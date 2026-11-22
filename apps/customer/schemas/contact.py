"""A customer's email and phone as every answer and the export give them: only to whoever sees the customers' contact
details (``base.view_customer_contact``), null to anyone else."""

from ninja import Field

from base.sensitive import CUSTOMER_CONTACT

EMAIL = Field(None, description="Email.", json_schema_extra=CUSTOMER_CONTACT)
PHONE = Field(None, description="Phone, in international format.", json_schema_extra=CUSTOMER_CONTACT)
