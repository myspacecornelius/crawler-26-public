"""
Stripe billing integration for LeadFactory.

Handles checkout session creation, webhook processing, and customer portal.
Requires STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET environment variables.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import User, CreditTransaction, ProcessedStripeEvent
from .settings import settings

logger = logging.getLogger("leadfactory.billing")

# ── Stripe config (from centralised settings) ─

stripe.api_key = settings.stripe_secret_key
STRIPE_WEBHOOK_SECRET = settings.stripe_webhook_secret
STRIPE_PUBLISHABLE_KEY = settings.stripe_publishable_key

FRONTEND_URL = settings.frontend_url

# ── Plan definitions ───────────────────────────

PLANS = {
    "starter": {
        "name": "Starter",
        "price_cents": 0,
        "credits_monthly": 500,
        "stripe_price_id": settings.stripe_price_starter,
    },
    "pro": {
        "name": "Pro",
        "price_cents": 4900,
        "credits_monthly": 5000,
        "stripe_price_id": settings.stripe_price_pro,
    },
    "scale": {
        "name": "Scale",
        "price_cents": 14900,
        "credits_monthly": 25000,
        "stripe_price_id": settings.stripe_price_scale,
    },
}

CREDIT_PACKS = {
    "1k": {
        "name": "1,000 Credits",
        "credits": 1000,
        "price_cents": 1900,
        "stripe_price_id": settings.stripe_price_credits_1k,
    },
    "5k": {
        "name": "5,000 Credits",
        "credits": 5000,
        "price_cents": 7900,
        "stripe_price_id": settings.stripe_price_credits_5k,
    },
    "10k": {
        "name": "10,000 Credits",
        "credits": 10000,
        "price_cents": 12900,
        "stripe_price_id": settings.stripe_price_credits_10k,
    },
}


# ── Helpers ────────────────────────────────────

async def get_or_create_stripe_customer(user: User, db: AsyncSession) -> str:
    """Ensure user has a Stripe customer ID, creating one if needed."""
    if user.stripe_customer_id:
        return user.stripe_customer_id

    customer = stripe.Customer.create(
        email=user.email,
        name=user.name,
        metadata={"user_id": str(user.id)},
    )
    user.stripe_customer_id = customer.id
    await db.commit()
    return customer.id


async def create_checkout_session(
    user: User,
    db: AsyncSession,
    plan: Optional[str] = None,
    credit_pack: Optional[str] = None,
) -> str:
    """Create a Stripe Checkout Session and return the URL."""
    customer_id = await get_or_create_stripe_customer(user, db)

    if plan and plan in PLANS and plan != "starter":
        plan_info = PLANS[plan]
        if not plan_info["stripe_price_id"]:
            raise ValueError(f"Stripe price ID not configured for plan: {plan}")
        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="subscription",
            line_items=[{"price": plan_info["stripe_price_id"], "quantity": 1}],
            success_url=f"{FRONTEND_URL}/dashboard/settings?checkout=success",
            cancel_url=f"{FRONTEND_URL}/dashboard/settings?checkout=cancelled",
            metadata={"user_id": str(user.id), "plan": plan},
            idempotency_key=f"checkout-plan-{user.id}-{plan}",
        )
    elif credit_pack and credit_pack in CREDIT_PACKS:
        pack_info = CREDIT_PACKS[credit_pack]
        if not pack_info["stripe_price_id"]:
            raise ValueError(f"Stripe price ID not configured for credit pack: {credit_pack}")
        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="payment",
            line_items=[{"price": pack_info["stripe_price_id"], "quantity": 1}],
            success_url=f"{FRONTEND_URL}/dashboard/settings?checkout=success",
            cancel_url=f"{FRONTEND_URL}/dashboard/settings?checkout=cancelled",
            metadata={"user_id": str(user.id), "credit_pack": credit_pack},
            idempotency_key=f"checkout-credits-{user.id}-{credit_pack}",
        )
    else:
        raise ValueError("Must specify a valid plan or credit_pack")

    return session.url


async def create_portal_session(user: User, db: AsyncSession) -> str:
    """Create a Stripe Billing Portal session and return the URL."""
    customer_id = await get_or_create_stripe_customer(user, db)
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{FRONTEND_URL}/dashboard/settings",
    )
    return session.url


# ── Webhook handling ───────────────────────────

async def handle_webhook(payload: bytes, sig_header: str, db: AsyncSession) -> dict:
    """Process a Stripe webhook event. Returns a status dict.

    Uses the processed_stripe_events table as an idempotency guard:
    if the event ID has already been recorded, return 200 immediately
    so Stripe treats the retry as successful without double-processing.
    """
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        logger.warning("Stripe webhook signature verification failed")
        raise ValueError("Invalid signature")
    except Exception as e:
        logger.error(f"Stripe webhook error: {e}")
        raise ValueError(f"Webhook error: {e}")

    event_id = event["id"]
    event_type = event["type"]

    # ── Idempotency guard ─────────────────────
    existing = await db.execute(
        select(ProcessedStripeEvent).where(ProcessedStripeEvent.stripe_event_id == event_id)
    )
    if existing.scalar_one_or_none() is not None:
        logger.info(f"Skipping already-processed Stripe event {event_id} ({event_type})")
        return {"status": "already_processed", "event_type": event_type}

    logger.info(f"Processing Stripe event: {event_id} ({event_type})")

    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(event["data"]["object"], db)
    elif event_type == "customer.subscription.updated":
        await _handle_subscription_updated(event["data"]["object"], db)
    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_deleted(event["data"]["object"], db)
    elif event_type == "invoice.paid":
        await _handle_invoice_paid(event["data"]["object"], db)
    else:
        logger.debug(f"Unhandled event type: {event_type}")

    # Record event as processed (after successful handling)
    db.add(ProcessedStripeEvent(stripe_event_id=event_id, event_type=event_type))
    await db.commit()

    return {"status": "ok", "event_type": event_type}


async def _find_user_by_customer_id(customer_id: str, db: AsyncSession) -> Optional[User]:
    result = await db.execute(
        select(User).where(User.stripe_customer_id == customer_id)
    )
    return result.scalar_one_or_none()


async def _find_user_by_metadata(metadata: dict, db: AsyncSession) -> Optional[User]:
    user_id = metadata.get("user_id")
    if not user_id:
        return None
    from uuid import UUID as _UUID
    result = await db.execute(select(User).where(User.id == _UUID(user_id)))
    return result.scalar_one_or_none()


async def _handle_checkout_completed(session_obj: dict, db: AsyncSession):
    """Handle successful checkout — update plan or add credits."""
    metadata = session_obj.get("metadata", {})
    user = await _find_user_by_metadata(metadata, db)
    if not user:
        user = await _find_user_by_customer_id(session_obj.get("customer", ""), db)
    if not user:
        logger.error(f"Checkout completed but user not found: {metadata}")
        return

    # Credit pack purchase
    credit_pack_slug = metadata.get("credit_pack")
    if credit_pack_slug and credit_pack_slug in CREDIT_PACKS:
        pack = CREDIT_PACKS[credit_pack_slug]
        user.credits_remaining += pack["credits"]
        tx = CreditTransaction(
            user_id=user.id,
            amount=pack["credits"],
            reason=f"purchase:{pack['name']}",
            balance_after=user.credits_remaining,
        )
        db.add(tx)
        await db.commit()
        logger.info(f"Added {pack['credits']} credits to user {user.id}")
        return

    # Subscription plan upgrade
    plan_slug = metadata.get("plan")
    if plan_slug and plan_slug in PLANS:
        plan_info = PLANS[plan_slug]
        user.plan = plan_slug
        user.credits_monthly = plan_info["credits_monthly"]
        user.credits_remaining = plan_info["credits_monthly"]
        user.stripe_subscription_id = session_obj.get("subscription")
        tx = CreditTransaction(
            user_id=user.id,
            amount=plan_info["credits_monthly"],
            reason=f"plan_upgrade:{plan_slug}",
            balance_after=user.credits_remaining,
        )
        db.add(tx)
        await db.commit()
        logger.info(f"Upgraded user {user.id} to plan {plan_slug}")


async def _handle_subscription_updated(subscription: dict, db: AsyncSession):
    """Handle subscription updates (plan changes)."""
    customer_id = subscription.get("customer")
    user = await _find_user_by_customer_id(customer_id, db)
    if not user:
        logger.warning(f"Subscription updated but user not found for customer: {customer_id}")
        return

    user.stripe_subscription_id = subscription["id"]
    await db.commit()


async def _handle_subscription_deleted(subscription: dict, db: AsyncSession):
    """Handle subscription cancellation — downgrade to starter."""
    customer_id = subscription.get("customer")
    user = await _find_user_by_customer_id(customer_id, db)
    if not user:
        logger.warning(f"Subscription deleted but user not found for customer: {customer_id}")
        return

    user.plan = "starter"
    user.credits_monthly = PLANS["starter"]["credits_monthly"]
    user.stripe_subscription_id = None
    tx = CreditTransaction(
        user_id=user.id,
        amount=0,
        reason="subscription_cancelled",
        balance_after=user.credits_remaining,
    )
    db.add(tx)
    await db.commit()
    logger.info(f"Downgraded user {user.id} to starter after subscription cancellation")


async def _handle_invoice_paid(invoice: dict, db: AsyncSession):
    """Handle recurring invoice payment — refill credits."""
    customer_id = invoice.get("customer")
    user = await _find_user_by_customer_id(customer_id, db)
    if not user:
        return

    # Only refill on recurring payments (not the first invoice)
    if invoice.get("billing_reason") == "subscription_cycle":
        plan_info = PLANS.get(user.plan)
        if plan_info:
            user.credits_remaining = plan_info["credits_monthly"]
            tx = CreditTransaction(
                user_id=user.id,
                amount=plan_info["credits_monthly"],
                reason="monthly_refill",
                balance_after=user.credits_remaining,
            )
            db.add(tx)
            await db.commit()
            logger.info(f"Monthly credit refill for user {user.id}: {plan_info['credits_monthly']} credits")
