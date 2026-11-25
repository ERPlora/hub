"""Input and output schemas of the printing app's operations (OpenAPI, live params, 422 per field).

They are also the JSON Schema of the assistant's tools, so every field says what it is. What a person names
aloud is accepted besides the id: a printer by its name («the kitchen one»), a job by the number of its
document («T-000123»). The document of a job travels structured, in the shape the app's renderer reads
(WORKBOOK «Contrato con la plataforma»); only an A4 job carries a page.
"""

from . import (
    claims as claims,
    devices as devices,
    fields as fields,
    health as health,
    jobs as jobs,
    printers as printers,
    settings as settings,
)
