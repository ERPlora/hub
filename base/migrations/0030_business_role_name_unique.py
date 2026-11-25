# Two roles of a business do not share a name, whatever their capitals. Reverting lets them again; the roles stay.

from django.db import migrations, models
from django.db.models.functions import Lower


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0029_support_access"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="businessrole",
            constraint=models.UniqueConstraint(Lower("name"), name="base_businessrole_name_unique"),
        ),
    ]
