"""Unit tests for handlers/broadcast.py: FSM flow for broadcast notifications."""

from unittest.mock import AsyncMock

import texts
from callbacks import ACTION_BACK, ACTION_CUSTOM, MessageCb, RecipientCb
from handlers.broadcast import (
    BroadcastForm,
    cancel_flow,
    choose_message,
    confirm_back,
    confirm_send,
    message_text_hint,
    next_to_message,
    receive_custom_text,
    recipients_text_hint,
    select_all,
    start_broadcast,
    toggle_recipient,
)
from keyboards.broadcast import message_keyboard
from services.broadcast import BROADCAST_TEXT_MAX
from storage import MEMBER_APPROVED, Storage
from tests.fakes import (
    _FakeCallback,
    _FakeMessage,
    _FakeState,
    _inline_button_texts,
)


async def _seeded_storage(tmp_path, sender_role: str | None = "group_lead") -> Storage:
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Лід Групи", "lead", status=MEMBER_APPROVED)
    if sender_role:
        await storage.add_role(111, sender_role)
    await storage.upsert_member(222, "Іваненко Петро", "ivan", status=MEMBER_APPROVED)
    await storage.upsert_member(333, "Бондар Оля", "olya", status=MEMBER_APPROVED)
    return storage


# --- start_broadcast ---


async def test_start_broadcast_denied_for_student(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_APPROVED)
    msg = _FakeMessage(from_user_id=111)
    state = _FakeState()

    await start_broadcast(msg, state, storage)

    assert any(texts.NOT_ALLOWED_BROADCAST == text for text, _ in msg.answers)
    assert state.set_to is None


async def test_start_broadcast_opens_recipient_picker(tmp_path):
    storage = await _seeded_storage(tmp_path)
    msg = _FakeMessage(from_user_id=111)
    state = _FakeState()

    await start_broadcast(msg, state, storage)

    assert state.set_to == BroadcastForm.recipients
    assert len(msg.answers) == 1
    text, markup = msg.answers[0]
    assert texts.BROADCAST_PROMPT.split("{")[0] in text
    buttons = _inline_button_texts(markup)
    assert buttons[0] == texts.BROADCAST_ALL_BUTTON
    # The sender is never a recipient.
    assert all("Лід Групи" not in label for label in buttons)


async def test_start_broadcast_empty_roster(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Лід Групи", "lead", status=MEMBER_APPROVED)
    await storage.add_role(111, "group_lead")
    msg = _FakeMessage(from_user_id=111)
    state = _FakeState()

    await start_broadcast(msg, state, storage)

    assert any(texts.BROADCAST_EMPTY == text for text, _ in msg.answers)
    assert state.set_to is None


# --- recipient picker ---


async def test_toggle_recipient(tmp_path):
    storage = await _seeded_storage(tmp_path)
    callback = _FakeCallback(111)
    state = _FakeState({"recipients": {}})

    await toggle_recipient(callback, state, storage, RecipientCb(user_id=222))

    assert (await state.get_data())["recipients"]["222"] is True
    assert len(callback.message.edits) == 1
    assert len(callback.answers) == 1


async def test_select_all_selects_then_clears(tmp_path):
    storage = await _seeded_storage(tmp_path)
    callback = _FakeCallback(111)
    state = _FakeState({"recipients": {}})

    await select_all(callback, state, storage)
    assert (await state.get_data())["recipients"] == {"222": True, "333": True}

    await select_all(callback, state, storage)
    assert (await state.get_data())["recipients"] == {}


async def test_select_all_adds_to_partial_selection(tmp_path):
    storage = await _seeded_storage(tmp_path)
    callback = _FakeCallback(111)
    state = _FakeState({"recipients": {"222": True}})

    await select_all(callback, state, storage)

    assert (await state.get_data())["recipients"] == {"222": True, "333": True}


async def test_select_all_drops_stale_keys(tmp_path):
    storage = await _seeded_storage(tmp_path)
    callback = _FakeCallback(111)
    state = _FakeState({"recipients": {"222": True, "999": True}})

    await select_all(callback, state, storage)

    assert (await state.get_data())["recipients"] == {"222": True, "333": True}


async def test_select_all_full_visible_with_stale_key_clears(tmp_path):
    storage = await _seeded_storage(tmp_path)
    callback = _FakeCallback(111)
    state = _FakeState({"recipients": {"222": True, "333": True, "999": True}})

    await select_all(callback, state, storage)

    assert (await state.get_data())["recipients"] == {}


async def test_recipients_text_hint_reshows_picker(tmp_path):
    storage = await _seeded_storage(tmp_path)
    msg = _FakeMessage(from_user_id=111, text="не кнопка")
    state = _FakeState({"recipients": {}})

    await recipients_text_hint(msg, state, storage)

    text, markup = msg.answers[0]
    assert texts.BROADCAST_PICK_HINT in text
    assert texts.BROADCAST_ALL_BUTTON in _inline_button_texts(markup)[0]


async def test_message_text_hint_reshows_picker(tmp_path):
    msg = _FakeMessage(from_user_id=111, text="не кнопка")
    state = _FakeState({"recipients": {"222": True}})

    await message_text_hint(msg, state)

    text, markup = msg.answers[0]
    assert text == f"{texts.BROADCAST_MSG_HINT}\n\n{texts.BROADCAST_MSG_PROMPT}"
    assert markup == message_keyboard()


# --- message step ---


async def test_next_without_selection_alerts(tmp_path):
    callback = _FakeCallback(111)
    state = _FakeState({"recipients": {}})

    await next_to_message(callback, state)

    assert any(
        args and args[0] == texts.BROADCAST_NO_RECIPIENTS for args, _ in callback.answers
    )
    assert state.set_to is None


async def test_next_with_selection_opens_message_step(tmp_path):
    callback = _FakeCallback(111)
    state = _FakeState({"recipients": {"222": True}})

    await next_to_message(callback, state)

    assert state.set_to == BroadcastForm.message
    assert callback.message.edits[0][0] == texts.BROADCAST_MSG_PROMPT


async def test_choose_predefined_message_reaches_confirm(tmp_path):
    storage = await _seeded_storage(tmp_path)
    callback = _FakeCallback(111)
    state = _FakeState({"recipients": {"222": True}})

    await choose_message(callback, state, storage, MessageCb(code="test"))

    assert state.set_to == BroadcastForm.confirm
    data = await state.get_data()
    assert data["message_code"] == "test"
    assert data["message_text"] == texts.BROADCAST_TEXT
    text = callback.message.edits[0][0]
    assert texts.BROADCAST_CONFIRM_QUESTION in text
    assert texts.BROADCAST_TEXT in text


async def test_choose_invalid_message_alerts_stale(tmp_path):
    storage = Storage(tmp_path)
    callback = _FakeCallback(111)
    state = _FakeState({"recipients": {"222": True}})

    await choose_message(callback, state, storage, MessageCb(code="nope"))

    assert any(
        args and args[0] == texts.STALE_CALLBACK and kwargs.get("show_alert") is True
        for args, kwargs in callback.answers
    )
    assert state.set_to is None


async def test_message_back_returns_to_recipients(tmp_path):
    storage = await _seeded_storage(tmp_path)
    callback = _FakeCallback(111)
    state = _FakeState({"recipients": {"222": True}})

    await choose_message(callback, state, storage, MessageCb(code=ACTION_BACK))

    assert state.set_to == BroadcastForm.recipients
    assert texts.BROADCAST_PROMPT.split("{")[0] in callback.message.edits[0][0]


async def test_choose_custom_message_prompts_for_text(tmp_path):
    storage = Storage(tmp_path)
    callback = _FakeCallback(111)
    state = _FakeState({"recipients": {"222": True}})

    await choose_message(callback, state, storage, MessageCb(code=ACTION_CUSTOM))

    assert state.set_to == BroadcastForm.custom_text
    assert callback.message.edits[0][0] == texts.BROADCAST_CUSTOM_PROMPT.format(
        limit=BROADCAST_TEXT_MAX
    )


async def test_receive_custom_text_valid_reaches_confirm(tmp_path):
    storage = await _seeded_storage(tmp_path)
    msg = _FakeMessage(from_user_id=111, text="Привіт усім")
    state = _FakeState({"recipients": {"222": True}})

    await receive_custom_text(msg, state, storage)

    assert state.set_to == BroadcastForm.confirm
    data = await state.get_data()
    assert data["message_code"] == ACTION_CUSTOM
    assert data["message_text"] == "Привіт усім"
    assert texts.BROADCAST_CONFIRM_QUESTION in msg.answers[0][0]


async def test_receive_custom_text_empty_reprompts(tmp_path):
    storage = Storage(tmp_path)
    msg = _FakeMessage(from_user_id=111, text="   ")
    state = _FakeState({"recipients": {"222": True}})

    await receive_custom_text(msg, state, storage)

    assert state.set_to is None
    assert msg.answers[0][0] == texts.BROADCAST_CUSTOM_EMPTY


async def test_receive_custom_text_too_long_reprompts(tmp_path):
    storage = Storage(tmp_path)
    msg = _FakeMessage(from_user_id=111, text="а" * (BROADCAST_TEXT_MAX + 1))
    state = _FakeState({"recipients": {"222": True}})

    await receive_custom_text(msg, state, storage)

    assert state.set_to is None
    assert msg.answers[0][0] == texts.BROADCAST_CUSTOM_TOO_LONG.format(
        limit=BROADCAST_TEXT_MAX
    )


async def test_confirm_back_returns_to_message_step(tmp_path):
    callback = _FakeCallback(111)
    state = _FakeState({"recipients": {"222": True}, "message_text": texts.BROADCAST_TEXT})

    await confirm_back(callback, state)

    assert state.set_to == BroadcastForm.message
    assert callback.message.edits[0][0] == texts.BROADCAST_MSG_PROMPT


async def test_cancel_flow_clears_state(tmp_path):
    storage = Storage(tmp_path)
    callback = _FakeCallback(111)
    state = _FakeState({"recipients": {"222": True}})

    await cancel_flow(callback, state, storage)

    assert state.cleared
    assert texts.CANCELLED in callback.message.answers[0][0]


# --- confirm_send ---


async def test_confirm_send_delivers_excluding_sender(tmp_path):
    storage = await _seeded_storage(tmp_path)
    bot = AsyncMock()
    callback = _FakeCallback(111, bot=bot)
    state = _FakeState(
        {
            "recipients": {"222": True},
            "message_code": "test",
            "message_text": texts.BROADCAST_TEXT,
        }
    )

    await confirm_send(callback, state, storage)

    assert state.cleared
    assert bot.send_message.call_count == 1
    assert bot.send_message.call_args[0] == (222, texts.BROADCAST_TEXT)
    assert texts.BROADCAST_SUCCESS.format(count=1) in callback.message.answers[0][0]


async def test_confirm_send_clears_state_before_sending(tmp_path):
    storage = await _seeded_storage(tmp_path)
    state = _FakeState(
        {
            "recipients": {"222": True},
            "message_code": "test",
            "message_text": texts.BROADCAST_TEXT,
        }
    )
    cleared_at_send: list[bool] = []

    async def _record(chat_id, text, **kwargs):
        cleared_at_send.append(state.cleared)

    bot = AsyncMock()
    bot.send_message = AsyncMock(side_effect=_record)
    callback = _FakeCallback(111, bot=bot)

    await confirm_send(callback, state, storage)

    assert cleared_at_send == [True]
    assert bot.send_message.call_count == 1


async def test_confirm_send_partial_failure_reports(tmp_path):
    storage = await _seeded_storage(tmp_path)
    bot = AsyncMock()
    bot.send_message = AsyncMock(side_effect=[None, RuntimeError("boom")])
    bot.get_chat = AsyncMock(side_effect=RuntimeError("no chat"))
    callback = _FakeCallback(111, bot=bot)
    state = _FakeState(
        {
            "recipients": {"222": True, "333": True},
            "message_code": "test",
            "message_text": texts.BROADCAST_TEXT,
        }
    )

    await confirm_send(callback, state, storage)

    assert state.cleared
    expected = texts.BROADCAST_SUCCESS_PARTIAL.format(delivered=1, failed=1)
    assert callback.message.answers[0][0] == expected


async def test_confirm_send_stale_selection_sends_nothing(tmp_path):
    storage = await _seeded_storage(tmp_path)
    bot = AsyncMock()
    callback = _FakeCallback(111, bot=bot)
    state = _FakeState(
        {
            "recipients": {"999": True},
            "message_code": "test",
            "message_text": texts.BROADCAST_TEXT,
        }
    )

    await confirm_send(callback, state, storage)

    assert state.cleared
    assert any(
        args and args[0] == texts.STALE_CALLBACK and kwargs.get("show_alert") is True
        for args, kwargs in callback.answers
    )
    bot.send_message.assert_not_called()


async def test_confirm_send_denied_for_student(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_APPROVED)
    bot = AsyncMock()
    callback = _FakeCallback(111, bot=bot)
    state = _FakeState(
        {"recipients": {"222": True}, "message_text": texts.BROADCAST_TEXT}
    )

    await confirm_send(callback, state, storage)

    assert state.cleared
    assert any(
        args and args[0] == texts.NOT_ALLOWED_BROADCAST for args, _ in callback.answers
    )
    bot.send_message.assert_not_called()


async def test_confirm_send_empty_message_is_stale(tmp_path):
    storage = await _seeded_storage(tmp_path)
    bot = AsyncMock()
    callback = _FakeCallback(111, bot=bot)
    state = _FakeState({"recipients": {"222": True}, "message_text": ""})

    await confirm_send(callback, state, storage)

    assert state.cleared
    assert any(
        args and args[0] == texts.STALE_CALLBACK for args, _ in callback.answers
    )
    bot.send_message.assert_not_called()
