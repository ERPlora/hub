"""What puts a menu on sale or takes it off the till (``combo.combo.set_active``, COMBO-F03)."""

from ninja import Field

from apps.combo.schemas.references import ComboRefIn


class ComboOnSaleIn(ComboRefIn):
    is_active: bool = Field(description="On sale (true) or off the till (false); it stays on the list of menus.")
