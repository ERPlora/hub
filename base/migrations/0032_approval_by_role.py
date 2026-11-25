# The record of approvals keeps also what was done by whoever may do it themselves: with no pass and no limit in time. Every
# row the code of before writes still passes the check. Going back is refused while a row says it was done by a role.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0031_support_entry'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='approval',
            name='base_approval_way',
        ),
        migrations.AlterField(
            model_name='approval',
            name='expires_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='valid until'),
        ),
        migrations.AlterField(
            model_name='approval',
            name='token_digest',
            field=models.CharField(blank=True, max_length=64, null=True, unique=True, verbose_name='pass digest'),
        ),
        migrations.AlterField(
            model_name='approval',
            name='way',
            field=models.CharField(choices=[('pin', 'PIN'), ('badge', 'Badge'), ('role', 'Their role')], max_length=8, verbose_name='approved with'),
        ),
        migrations.AddConstraint(
            model_name='approval',
            constraint=models.CheckConstraint(condition=models.Q(('way__in', ['pin', 'badge', 'role'])), name='base_approval_way'),
        ),
    ]
