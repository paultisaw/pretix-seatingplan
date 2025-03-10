from django.apps import AppConfig
from django.utils.translation import gettext_lazy

__version__ = "1.0.0"


class PluginApp(AppConfig):
    name = "pretix.plugins.seating_plan"
    verbose_name = "Seating Plan"

    class PretixPluginMeta:
        name = gettext_lazy("Seating Plan")
        author = "Evey"
        description = gettext_lazy("Ticket buyers can choose their own seats on an interactive seating plan. We can handle every venue from small cinemas or ballrooms up to large-scale stadiums.")
        visible = True
        version = __version__
        category = "FEATURE"
        compatibility = "pretix>=2.7.0"

    def ready(self):
        from . import signals  # NOQA

    def is_available(self, event):
        return True