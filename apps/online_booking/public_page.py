"""What only the public booking page needs: whose page it is (the business's name, its logo and the privacy policy its
form links to) and the trap field of its form, which a person never sees and a robot fills in. The customer's personal
link names the same business, with the same logo."""

from typing import Annotated

from django.conf import settings
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext, system_context
from live.operations import get as get_operation
from ninja import Field, Schema
from pydantic import model_validator
from pydantic.json_schema import SkipJsonSchema

from apps.online_booking.logo import logo_url

BUSINESS = "base.business.get"
#: ERPlora's privacy policy on erplora.com. The business decides on its customers' details and ERPlora processes
#: them on its behalf, as that policy says; a business has no policy of its own to link here.
PRIVACY_POLICY_PATH = "/legal/privacy/"
# Says nothing of why: a robot learns nothing, and a person still has a way to book.
NOT_TAKEN = _("We could not take this booking. Try again, or call the business.")


BusinessName = Annotated[str, Field(description="The business's name, as erplora.com registered it; empty in a demo.")]
LogoUrl = Annotated[str, Field(description="Where the business's own address serves its logo; empty = none.")]


class LinkOwnerOut(Schema):
    business_name: BusinessName
    logo_url: LogoUrl

    @classmethod
    def owner(cls, ctx: OperationContext, logo: str) -> dict:
        """Whose page or link it is, for ``ctx``'s business: read as the platform, as nobody signed in reads it."""
        business = get_operation(BUSINESS)
        return {
            "business_name": business(system_context(ctx.scope), business.input()).name,
            "logo_url": logo_url(ctx.scope, logo),
        }


class PageOwnerOut(Schema):
    business_name: BusinessName
    privacy_policy_url: str = Field(description="The privacy policy the booking form links to.")
    logo_url: LogoUrl

    @classmethod
    def owner(cls, ctx: OperationContext, logo: str) -> dict:
        privacy = f"{settings.SAAS_URL.rstrip('/')}{PRIVACY_POLICY_PATH}"
        return LinkOwnerOut.owner(ctx, logo) | {"privacy_policy_url": privacy}


class TrapIn(Schema):
    # Out of the OpenAPI and the assistant's tools: only the page's form sends it, and a person leaves it empty.
    # Any value, not only text: a wrong type would be refused by name, and the refusal never names this field.
    website: SkipJsonSchema[object] = Field("", description="The form's hidden field: empty, or the booking is refused.")

    @model_validator(mode="after")
    def _not_a_robot(self):
        if self.website:
            raise ValueError(str(NOT_TAKEN))
        return self
