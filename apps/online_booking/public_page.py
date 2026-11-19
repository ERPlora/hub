"""What only the public booking page needs: whose page it is (the business's name and the privacy policy its form
links to) and the trap field of its form, which a person never sees and a robot fills in."""

from django.conf import settings
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext, system_context
from live.operations import get as get_operation
from ninja import Field, Schema
from pydantic import model_validator
from pydantic.json_schema import SkipJsonSchema

BUSINESS = "base.business.get"
#: ERPlora's privacy policy on erplora.com. The business decides on its customers' details and ERPlora processes
#: them on its behalf, as that policy says; a business has no policy of its own to link here.
PRIVACY_POLICY_PATH = "/legal/privacy/"
# Says nothing of why: a robot learns nothing, and a person still has a way to book.
NOT_TAKEN = _("We could not take this booking. Try again, or call the business.")


class PageOwnerOut(Schema):
    business_name: str = Field(description="The business's name, as erplora.com registered it; empty in a demo.")
    privacy_policy_url: str = Field(description="The privacy policy the booking form links to.")

    @classmethod
    def owner(cls, ctx: OperationContext) -> dict:
        """Whose page it is, for ``ctx``'s business: read as the platform, as nobody signed in reads the page."""
        business = get_operation(BUSINESS)
        return {
            "business_name": business(system_context(ctx.scope), business.input()).name,
            "privacy_policy_url": f"{settings.SAAS_URL.rstrip('/')}{PRIVACY_POLICY_PATH}",
        }


class TrapIn(Schema):
    # Out of the OpenAPI and the assistant's tools: only the page's form sends it, and a person leaves it empty.
    website: SkipJsonSchema[str] = Field("", description="The form's hidden field: empty, or the booking is refused.")

    @model_validator(mode="after")
    def _not_a_robot(self):
        if self.website:
            raise ValueError(str(NOT_TAKEN))
        return self
