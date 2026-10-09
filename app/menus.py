"""Menus an admin can grant to a user directly on the Access page.

Granting a menu works exactly like assigning the custom role of the same
name: the user's effective role names (deps.user_role_names) include the
menu's role name, so every existing role check — and the per-role
view/create/edit/delete grants on the Access page — applies unchanged.

Menus every user already has (Overview, Packages, Bookings, Travel List)
and the admin-only management menus (Users, Roles, Access) aren't listed.
The frontend mirrors this list in lib/menus.ts.
"""

# key (stored in users.menuAccess) -> (label shown on the Access page, role name it unlocks)
MENU_ACCESS: dict[str, tuple[str, str]] = {
    "upcoming-packages": ("Upcoming Packages", "upcoming packages"),
    "offers": ("Offer Section", "offer section"),
    "rooms": ("Room List", "room list"),
    "accounts": ("Account", "account"),
    "currency": ("Currency", "currency"),
    "dmc-accounts": ("DMC Account", "dmc account"),
    "hotel-vouchers": ("Hotel Voucher", "hotel voucher"),
}


def granted_menus(user_doc: dict | None) -> list[str]:
    """The user's granted menu keys, in MENU_ACCESS order, unknown keys dropped."""
    keys = set((user_doc or {}).get("menuAccess") or [])
    return [k for k in MENU_ACCESS if k in keys]


def menu_role_names(user_doc: dict | None) -> list[str]:
    """Role names unlocked by the user's granted menus (lower-case)."""
    return [MENU_ACCESS[k][1] for k in granted_menus(user_doc)]


def menu_labels(user_doc: dict | None) -> list[str]:
    """Display labels of the granted menus — used as Access-page card names."""
    return [MENU_ACCESS[k][0] for k in granted_menus(user_doc)]
