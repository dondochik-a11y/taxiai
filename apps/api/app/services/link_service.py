"""Account linking: a Telegram account and a web account become the same user.

One side (whichever holds a user_id) generates a short code; the other redeems
it. Two redemption directions:

- redeem_for_telegram: a web-first user made a code in the web app, then sends
  it to the bot — the bot's telegram_id is attached to that web user.
- redeem_for_web: a bot-first user made a code via the bot, then types it in
  the web app — the web app adopts the bot user's id.

Codes are 6 chars from an unambiguous alphabet, single-use, 15-min TTL.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.link_code import LinkCode
from app.models.user import User

# No 0/O/1/I/L — read-aloud- and type-friendly.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_LEN = 6
_TTL = timedelta(minutes=15)


def generate_code(db: Session, user_id) -> LinkCode:
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    # One active code per user: drop any previous (also clears expired rows).
    db.execute(delete(LinkCode).where(LinkCode.user_id == user_id))
    code = "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LEN))
    row = LinkCode(code=code, user_id=user_id, expires_at=datetime.now(timezone.utc) + _TTL)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _consume(db: Session, code: str) -> User:
    row = db.get(LinkCode, code.strip().upper())
    if row is None:
        raise HTTPException(status_code=404, detail="Код не найден или уже использован")
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        db.delete(row)
        db.commit()
        raise HTTPException(status_code=410, detail="Код истёк — сгенерируйте новый")
    user = db.get(User, row.user_id)
    if user is None:
        db.delete(row)
        db.commit()
        raise HTTPException(status_code=404, detail="Аккаунт не найден")
    db.delete(row)  # single-use; committed by the caller after its own changes
    return user


def redeem_for_telegram(db: Session, code: str, telegram_id: int) -> User:
    """Attach this telegram_id to the code's (web) user. If the telegram_id is
    already on another, bot-first account, detach it there first so the unique
    constraint holds; that old account is left intact but Telegram-less (no
    data is deleted — it's simply no longer reachable from Telegram)."""
    target = _consume(db, code)
    if target.telegram_id == telegram_id:
        db.commit()
        return target

    prior = db.execute(select(User).where(User.telegram_id == telegram_id)).scalar_one_or_none()
    if prior is not None and prior.id != target.id:
        prior.telegram_id = None
        db.flush()  # release the unique telegram_id before reassigning
    target.telegram_id = telegram_id
    db.commit()
    db.refresh(target)
    return target


def redeem_for_web(db: Session, code: str) -> User:
    """Return the code's (bot) user so the web app can adopt its id."""
    user = _consume(db, code)
    db.commit()
    db.refresh(user)
    return user
