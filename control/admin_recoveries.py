"""What the staff brings back into a business from one of its separate copies: the form of «Recover into the
business…» and the Recoveries list, registered by ``control.admin``."""

from django import forms
from django.contrib import admin
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext, gettext_lazy, ngettext, pgettext, pgettext_lazy

from base import admin as base_admin
from base.tenancy.recovery import recoverable_apps
from control.admin_shared import copy_said, utc
from control.models.copies import CopyRecovery


def recoverable_names(labels) -> str:
    """What the apps ``labels`` give back from a copy, as the staff reads it («Customers»); an app that no longer says
    so, by its label."""
    declared = recoverable_apps()
    return ", ".join(
        ", ".join(str(one.label) for one in declared[label]) if label in declared else label for label in labels
    )


class RecoverForm(forms.Form):
    """What the chosen copies give back into their businesses: the apps that say what they give back from a copy
    (``base.tenancy.recovery``), every one ticked; ``control.copy.recover`` checks the rest, copy by copy."""

    apps = forms.MultipleChoiceField(
        label=pgettext_lazy("recovery", "What to bring back"),
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [(label, recoverable_names([label])) for label in recoverable_apps()]
        self.fields["apps"].choices = choices
        self.fields["apps"].initial = [label for label, _name in choices]


class CopyRecoveryAdmin(base_admin.ReadOnlyAdmin):
    """What the staff asked to bring back into a business from one of its separate copies (BASE-F114): asked
    from Separate copies with «Recover into the business…», done by the worker; read only, for support too. Its
    results say, for each thing each app gives back, how many came back, how many not and how many came back without
    something; its page says why each did not, what each came back without (by its id in the copy: no personal data),
    and why an app gave nothing back."""

    # What the staff looks for at a glance, as Separate copies: three columns a phone shows whole (375 px). What was
    # asked, who asked it, when, when it was done and why each record did not come back are on its page.
    list_display = ("made_from", "status", "outcome")
    list_filter = ("status",)
    list_select_related = ("copy", "copy__hub")
    search_fields = ("copy__hub__slug", "copy__db_name")
    fields = ("copy", "status", "what", "outcome", "why_not", "notes", "asked_by", "asked_on", "done_on", "last_error")
    readonly_fields = fields

    class Media:
        # A long result breaks inside its cell, never pushing the list sideways on a phone.
        css = {"all": ["control/admin.css"]}

    @admin.display(description=gettext_lazy("separate copy"), ordering="copy__restore_point")
    def made_from(self, recovery: CopyRecovery) -> str:
        return copy_said(recovery.copy)

    @admin.display(description=pgettext_lazy("recovery", "what"))
    def what(self, recovery: CopyRecovery) -> str:
        return recoverable_names(recovery.apps)

    @admin.display(description=pgettext_lazy("recovery", "results"))
    def outcome(self, recovery: CopyRecovery) -> str:
        """How it went: while asked, what it brings back; done, what each app gave back; failed, that and why."""
        if recovery.status == CopyRecovery.Status.ASKED:
            return self.what(recovery)
        said = [self.result_said(result) for result in recovery.results]
        if recovery.status == CopyRecovery.Status.FAILED and recovery.last_error:
            said.append(recovery.last_error)
        return "; ".join(said) or self.get_empty_value_display()

    @admin.display(description=pgettext_lazy("recovery", "not brought back"))
    def why_not(self, recovery: CopyRecovery):
        return self.by_record(recovery, "reasons", "reason")

    @admin.display(description=pgettext_lazy("recovery", "notes"))
    def notes(self, recovery: CopyRecovery):
        """What a record that came back came back without, and why (a professional who has left since)."""
        return self.by_record(recovery, "notes", "note")

    def by_record(self, recovery: CopyRecovery, kept: str, said: str):
        """Each of the results' ``kept`` by the record's id in the copy, one a line: ``<id>: <said>``."""
        lines = [(one["id"], one[said]) for result in recovery.results for one in result.get(kept, [])]
        if not lines:
            return self.get_empty_value_display()
        return format_html("<ul>{}</ul>", format_html_join("", "<li>{}: {}</li>", lines))

    @admin.display(description=pgettext_lazy("separate copy", "asked at"), ordering="asked_at")
    def asked_on(self, recovery: CopyRecovery) -> str:
        return utc(recovery.asked_at)

    @admin.display(description=pgettext_lazy("recovery", "done at"), ordering="done_at")
    def done_on(self, recovery: CopyRecovery) -> str:
        return utc(recovery.done_at) if recovery.done_at else self.get_empty_value_display()

    @staticmethod
    def result_said(result: dict) -> str:
        """What one thing an app gives back gave, in words: «Services: 1 restored, 2 created, 1 not created, 1 with
        notes» (one came back without something, said on its page), or why it gave nothing. Its name is kept as the code
        writes it and said in the reader's language. A recovery noted before each thing was counted apart has no
        ``label`` (the app's names, together), and one noted before restores were counted has no ``restored``."""
        what, restored, created, missed, noted, why = (
            gettext(result["label"]) if "label" in result else recoverable_names([result["app"]]),
            result.get("restored", 0),
            result["created"],
            result["not_created"],
            result.get("noted", 0),
            result["refused"],
        )
        if why and not restored and not created and not missed:
            return pgettext("recovery", "%(what)s: nothing (%(why)s)") % {"what": what, "why": why}
        counts = []
        if restored:
            counts.append(ngettext("%(count)d restored", "%(count)d restored", restored) % {"count": restored})
        if created or not restored:
            counts.append(ngettext("%(count)d created", "%(count)d created", created) % {"count": created})
        if missed:
            counts.append(ngettext("%(count)d not created", "%(count)d not created", missed) % {"count": missed})
        if noted:
            counts.append(ngettext("%(count)d with notes", "%(count)d with notes", noted) % {"count": noted})
        said = pgettext("recovery", "%(what)s: %(counts)s") % {"what": what, "counts": ", ".join(counts)}
        if why:
            said = pgettext("recovery", "%(said)s, then stopped (%(why)s)") % {"said": said, "why": why}
        return said
