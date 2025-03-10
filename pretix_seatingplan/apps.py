from django.utils.translation import gettext_lazy

from . import __version__

try:
    from pretix.base.plugins import PluginConfig
except ImportError:
    raise RuntimeError("Please use pretix 2.7 or above to run this plugin!")


class PluginApp(PluginConfig):
    default = True
    name = "pretix_seatingplan"
    verbose_name = "Seating Plan"

    class PretixPluginMeta:
        name = gettext_lazy("SeatingPlan")
        author = "Paul Tissot-Daguette"
        description = gettext_lazy("Allow users to choose a ticket on a plan")
        visible = True
        version = __version__
        category = "FEATURE"
        compatibility = "pretix>=2.7.0"

    def ready(self):
        from . import signals  # NOQA

    def is_available(self, event):
        return True
