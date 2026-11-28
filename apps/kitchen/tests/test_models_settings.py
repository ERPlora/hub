"""The kitchen display settings and the rules the database itself keeps for them."""

from .conftest import HUB_DB, refused

pytestmark = HUB_DB


def test_the_settings_are_one_row_with_the_factory_values():
    from apps.kitchen.models.settings import KitchenSettings

    settings = KitchenSettings.objects.get()
    assert (
        settings.show_timer,
        settings.warning_minutes,
        settings.critical_minutes,
        settings.color_coding,
        settings.sound_enabled,
        settings.sound_volume,
        settings.sound_tone,
        settings.print_pass,
        settings.works_from_screen,
        settings.default_order_type,
    ) == (True, 15, 30, True, True, 70, "chime", False, True, "dine_in")
    assert refused(lambda: KitchenSettings.objects.create())


def test_the_settings_keep_their_ranges():
    from apps.kitchen.models.settings import KitchenSettings

    def save(**fields):
        def build():
            KitchenSettings.objects.update(**fields)

        return build

    assert refused(save(warning_minutes=0))
    assert refused(save(critical_minutes=121))
    assert refused(save(warning_minutes=30, critical_minutes=30))
    assert refused(save(sound_volume=101))
    assert refused(save(sound_tone="siren"))
    assert refused(save(default_order_type="drive_in"))
