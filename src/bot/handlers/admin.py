"""Handlers for admin actions."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.config import Config
from bot.keyboards.callbacks import AdminAction, AdminCallback
from database.repositories.organization import OrganizationRepository
from database.repositories.organization_category import OrganizationCategoryRepository

router = Router(name="admin")


class AdminStates(StatesGroup):
    waiting_category_input = State()
    waiting_organization_input = State()


@router.callback_query(AdminCallback.filter(F.action == AdminAction.ADD_CATEGORY))
async def add_category(
    callback: CallbackQuery,
    state: FSMContext,
    config: Config,
    callback_data: AdminCallback,
):
    """Start adding new category."""
    admin_ids = config.bot.admin_ids
    if callback.from_user.id not in admin_ids:
        await callback.answer("❌ У вас нет прав для этой операции", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_category_input)
    await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
        "📝 <b>Добавление категории</b>\n\n"
        "Введите данные в формате:\n"
        "<code>Название категории</code>\n\n"
        "Например:\n"
        "<code>Медицинские учреждения</code>\n\n"
        "Или нажмите 'Отмена' для возврата.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data=AdminCallback(action=AdminAction.CANCEL).pack(),
                    )
                ]
            ]
        ),
    )
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == AdminAction.ADD_ORGANIZATION))
async def add_organization(
    callback: CallbackQuery,
    state: FSMContext,
    config: Config,
    callback_data: AdminCallback,
):
    """Start adding new organization."""
    admin_ids = config.bot.admin_ids
    if callback.from_user.id not in admin_ids:
        await callback.answer("❌ У вас нет прав для этой операции", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_organization_input)
    await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
        "📝 <b>Добавление организации</b>\n\n"
        "Введите данные в формате:\n"
        "<code>Название организации\n\n"
        "Адрес\n\n"
        "Телефон (не обязательно)\n\n"
        "ID категории</code>\n\n"
        "Пример:\n"
        "<code>Поликлиника №1\n\n"
        "ул. Ленина, 10\n\n"
        "88002000600\n\n"
        "1</code>\n\n"
        "Или нажмите 'Отмена' для возврата.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data=AdminCallback(action=AdminAction.CANCEL).pack(),
                    )
                ]
            ]
        ),
    )
    await callback.answer()


@router.message(AdminStates.waiting_category_input, F.text)
async def process_category_input(
    message: Message,
    state: FSMContext,
    config: Config,
    organization_category_repo: OrganizationCategoryRepository,
):
    """Process category input from admin."""
    admin_ids = config.bot.admin_ids
    if not message.from_user or message.from_user.id not in admin_ids:
        await message.answer("❌ У вас нет прав для этой операции")
        return

    if message.text is None:
        await message.answer("❌ Ошибка обработки текста")

    category_name = message.text.strip()  # ty: ignore [possibly-missing-attribute]

    if not category_name:
        await message.answer("❌ Название категории не может быть пустым")
        return

    try:
        # Check if category already exists
        existing = await organization_category_repo.get_by_name(category_name)
        if existing:
            await message.answer(f"❌ Категория '{category_name}' уже существует")
            await state.clear()
            return

        # Add new category
        new_category = await organization_category_repo.create(name=category_name)
        await organization_category_repo.session.commit()

        await message.answer(
            f"✅ Категория '{category_name}' ({new_category.id}) успешно добавлена"
        )

    except Exception as e:
        await message.answer(f"❌ Ошибка при добавлении категории: {str(e)}")

    await state.clear()


@router.message(AdminStates.waiting_organization_input, F.text)
async def process_organization_input(
    message: Message,
    state: FSMContext,
    config: Config,
    organization_repo: OrganizationRepository,
    organization_category_repo: OrganizationCategoryRepository,
):
    """Process organization input from admin."""
    admin_ids = config.bot.admin_ids
    if not message.from_user or message.from_user.id not in admin_ids:
        await message.answer("❌ У вас нет прав для этой операции")
        return

    if message.text is None:
        await message.answer("❌ Ошибка обработки текста")

    # Parse input (separated by empty lines)
    parts = [p.strip() for p in message.text.strip().split("\n\n")]  # ty: ignore [possibly-missing-attribute]

    if len(parts) < 3:
        await message.answer(
            "❌ Неверный формат. Нужно ввести:\n"
            "1. Название организации\n"
            "2. Адрес\n"
            "3. ID категории\n"
            "4. Телефон (не обязательно)"
        )
        return

    try:
        # Extract data
        name = parts[0]
        address = parts[1]

        # Phone is optional (might be in parts[2] or parts[3])
        phone = None
        category_id = None

        if len(parts) == 3:
            # Only 3 parts: name, address, category_id
            category_id = int(parts[2])
        elif len(parts) >= 4:
            # 4 or more parts: name, address, phone, category_id
            phone = parts[2] if parts[2] else None
            category_id = int(parts[3])

        # Validate category exists
        category = await organization_category_repo.get(category_id or 1)
        if not category:
            await message.answer(f"❌ Категория с ID {category_id} не найдена")
            await state.clear()
            return

        # Add new organization
        new_org = await organization_repo.create(
            name=name, address=address, phone=phone, category=category_id
        )
        await organization_repo.session.commit()

        await message.answer(
            f"✅ Организация успешно добавлена:\n\n"
            f"<b>Id:</b> {new_org.id}\n"
            f"<b>Название:</b> {name}\n"
            f"<b>Адрес:</b> {address}\n"
            f"<b>Телефон:</b> {phone or 'не указан'}\n"
            f"<b>Категория:</b> {category.name}",
            parse_mode="HTML",
        )

    except ValueError:
        await message.answer("❌ ID категории должен быть числом")
    except Exception as e:
        await message.answer(f"❌ Ошибка при добавлении организации: {str(e)}")

    await state.clear()
