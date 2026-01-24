"""Handlers for organizations workflow."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.keyboards.builders import (
    build_organization_details_keyboard,
    build_organizations_list_keyboard,
    build_organizations_main_keyboard,
)
from bot.keyboards.callbacks import (
    CategoryListCallback,
    OrganizationAction,
    OrganizationListCallback,
    OrganizationMenuCallback,
    RouteAction,
    RouteMenuCallback,
)
from bot.states.bus_route import OrganizationStates
from database.repositories import OrganizationCategoryRepository, OrganizationRepository

router = Router(name="organizations")

# Constants
ORGANIZATIONS_PER_PAGE = 6


@router.callback_query(
    RouteMenuCallback.filter(F.action == RouteAction.START_ORGANIZATIONS)
)
async def show_organizations_menu(
    callback: CallbackQuery,
    state: FSMContext,
    organization_category_repo: OrganizationCategoryRepository,
):
    """
    Show main organizations menu with category grid.

    Triggered by "Организации" button from main menu.
    """
    await state.set_state(OrganizationStates.main_menu)

    # Get categories with pagination
    page = 0
    categories = await organization_category_repo.get_all(
        limit=ORGANIZATIONS_PER_PAGE, offset=page * ORGANIZATIONS_PER_PAGE
    )
    total_count = await organization_category_repo.count()
    total_pages = (total_count + ORGANIZATIONS_PER_PAGE - 1) // ORGANIZATIONS_PER_PAGE

    await state.update_data(current_page=page, total_pages=total_pages)

    text = "🏢 <b>Организации</b>\n\nВыберите категорию:"

    await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
        text=text,
        reply_markup=build_organizations_main_keyboard(categories, page, total_pages),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(
    OrganizationMenuCallback.filter(F.action == OrganizationAction.PREV_PAGE)
)
@router.callback_query(
    OrganizationMenuCallback.filter(F.action == OrganizationAction.NEXT_PAGE)
)
async def navigate_categories(
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: OrganizationMenuCallback,
    organization_category_repo: OrganizationCategoryRepository,
):
    """Handle pagination navigation in categories list."""
    page = callback_data.page
    current_state = await state.get_state()

    if current_state != OrganizationStates.main_menu.state:
        await callback.answer("❌ Недопустимая операция", show_alert=True)
        return

    # Get categories for the requested page
    categories = await organization_category_repo.get_all(
        limit=ORGANIZATIONS_PER_PAGE, offset=page * ORGANIZATIONS_PER_PAGE
    )

    if not categories and page > 0:
        # If page is empty but not the first page, go back one page
        page -= 1
        categories = await organization_category_repo.get_all(
            limit=ORGANIZATIONS_PER_PAGE, offset=page * ORGANIZATIONS_PER_PAGE
        )

    total_count = await organization_category_repo.count()
    total_pages = (total_count + ORGANIZATIONS_PER_PAGE - 1) // ORGANIZATIONS_PER_PAGE

    await state.update_data(current_page=page, total_pages=total_pages)

    if not categories:
        await callback.answer("❌ Нет категорий на этой странице", show_alert=True)
        return

    text = "🏢 <b>Организации</b>\n\nВыберите категорию:"

    await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
        text=text,
        reply_markup=build_organizations_main_keyboard(categories, page, total_pages),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(CategoryListCallback.filter())
async def select_category(
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: CategoryListCallback,
    organization_category_repo: OrganizationCategoryRepository,
    organization_repo: OrganizationRepository,
):
    """
    Handle category selection and show organizations in that category.
    """
    await state.set_state(OrganizationStates.organization_selection)

    # Get category name
    category = await organization_category_repo.get(callback_data.category_id)
    if not category:
        await callback.answer("❌ Категория не найдена", show_alert=True)
        return

    # Get organizations for this category with pagination
    page = callback_data.page
    organizations = await organization_repo.get_by_category(
        category_id=callback_data.category_id,
        limit=ORGANIZATIONS_PER_PAGE,
        offset=page * ORGANIZATIONS_PER_PAGE,
    )

    total_count = await organization_repo.count_by_category(callback_data.category_id)
    total_pages = (total_count + ORGANIZATIONS_PER_PAGE - 1) // ORGANIZATIONS_PER_PAGE

    await state.update_data(
        selected_category_id=callback_data.category_id,
        selected_category_name=category.name,
        current_page=page,
        total_pages=total_pages,
    )

    text = f"🏢 <b>Организации:</b> {category.name}\n\nВыберите организацию:"

    await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
        text=text,
        reply_markup=build_organizations_list_keyboard(
            organizations=organizations,
            category_id=callback_data.category_id,
            page=page,
            total_pages=total_pages,
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(OrganizationListCallback.filter())
async def select_organization(
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: OrganizationListCallback,
    organization_repo: OrganizationRepository,
    organization_category_repo: OrganizationCategoryRepository,
):
    """
    Show detailed information about selected organization.
    """
    await state.set_state(OrganizationStates.organization_details)

    # Get organization data
    organization = await organization_repo.get(callback_data.organization_id)
    if not organization:
        await callback.answer("❌ Организация не найдена", show_alert=True)
        return

    # Get category name
    category = await organization_category_repo.get(organization.category)
    category_name = category.name if category else "Неизвестная категория"

    # Format phone number if exists
    phone_text = organization.phone if organization.phone else "не указан"

    text = (
        f"🏢 <b>{organization.name}</b>\n\n"
        f"📍  <b>Адрес:</b> {organization.address}\n"
        f"📞 <b>Телефон:</b> <code>{phone_text}</code>\n"
        f"🏷️ <b>Категория:</b> {category_name}"
    )

    await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
        text=text,
        reply_markup=build_organization_details_keyboard(
            organization_id=organization.id,
            category_id=callback_data.category_id or organization.category,
            page=callback_data.page,
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(
    OrganizationMenuCallback.filter(F.action == OrganizationAction.BACK)
)
async def handle_back_navigation(
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: OrganizationMenuCallback,
    organization_category_repo: OrganizationCategoryRepository,
    organization_repo: OrganizationRepository,
):
    """
    Handle back navigation in organization menu hierarchy.
    """
    current_state = await state.get_state()
    data = await state.get_data()

    if current_state == OrganizationStates.organization_details.state:
        # Return to organization list
        await state.set_state(OrganizationStates.organization_selection)

        # Get category name
        category_id = callback_data.category_id or data.get("selected_category_id")
        if not category_id:
            await callback.answer("❌ Ошибка навигации", show_alert=True)
            return

        category = await organization_category_repo.get(category_id)
        if not category:
            await callback.answer("❌ Категория не найдена", show_alert=True)
            return

        # Get organizations for current page
        page = callback_data.page or data.get("current_page", 0)
        organizations = await organization_repo.get_by_category(
            category_id=category_id,
            limit=ORGANIZATIONS_PER_PAGE,
            offset=page * ORGANIZATIONS_PER_PAGE,
        )

        total_count = await organization_repo.count_by_category(category_id)
        total_pages = (total_count + ORGANIZATIONS_PER_PAGE - 1) // ORGANIZATIONS_PER_PAGE

        await state.update_data(
            selected_category_id=category_id,
            selected_category_name=category.name,
            current_page=page,
            total_pages=total_pages,
        )

        text = f"🏢 <b>Организации:</b> {category.name}\n\nВыберите организацию:"

        await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
            text=text,
            reply_markup=build_organizations_list_keyboard(
                organizations=organizations,
                category_id=category_id,
                page=page,
                total_pages=total_pages,
            ),
            parse_mode="HTML",
        )

    elif current_state == OrganizationStates.organization_selection.state:
        # Return to category selection
        await state.set_state(OrganizationStates.main_menu)

        # Get categories for current page
        page = callback_data.page or data.get("current_page", 0)
        categories = await organization_category_repo.get_all(
            limit=ORGANIZATIONS_PER_PAGE, offset=page * ORGANIZATIONS_PER_PAGE
        )

        total_count = await organization_category_repo.count()
        total_pages = (total_count + ORGANIZATIONS_PER_PAGE - 1) // ORGANIZATIONS_PER_PAGE

        await state.update_data(current_page=page, total_pages=total_pages)

        text = "🏢 <b>Организации</b>\n\nВыберите категорию:"

        await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
            text=text,
            reply_markup=build_organizations_main_keyboard(categories, page, total_pages),
            parse_mode="HTML",
        )

    elif current_state == OrganizationStates.main_menu.state:
        # Return to main menu - handled by main router
        await callback.answer()
        return

    await callback.answer()


@router.callback_query(F.data.in_(["disabled_back", "disabled_forward", "page_info"]))
async def handle_disabled_navigation(callback: CallbackQuery):
    """
    Handle clicks on disabled navigation buttons in organization menu.

    Simply answers the callback without doing anything to prevent
    "query is too old" errors and provide feedback to user.
    """
    await callback.answer()


@router.callback_query(
    OrganizationMenuCallback.filter(F.action == OrganizationAction.SHOW_ORGANIZATIONS)
)
async def show_organizations_list(
    callback: CallbackQuery,
    callback_data: OrganizationMenuCallback,
    organization_repo: OrganizationRepository,
    organization_category_repo: OrganizationCategoryRepository,
):
    """Show organizations list for a category."""
    category_id: int = callback_data.category_id or 1
    page = callback_data.page

    # Get category
    category = await organization_category_repo.get(category_id)
    if not category:
        await callback.answer("Категория не найдена")
        return

    # Get organizations for this category with pagination
    per_page = 6
    offset = page * per_page
    organizations = await organization_repo.get_by_category(
        category_id, limit=per_page, offset=offset
    )

    # Count total organizations for pagination
    total_count = await organization_repo.count_by_category(category_id)
    total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1

    # Build and send keyboard
    keyboard = build_organizations_list_keyboard(
        organizations=organizations,
        category_id=category_id,
        page=page,
        total_pages=total_pages,
    )

    await callback.message.edit_text(  # ty: ignore [possibly-missing-attribute]
        f"🏢 Организации в категории: {category.name}", reply_markup=keyboard
    )
    await callback.answer()
