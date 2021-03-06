# Generated by Django 2.2.7 on 2019-11-20 09:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('katka', '0028_unique_commits'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='scmpipelinerun',
            options={'ordering': ['-created_at'], 'verbose_name': 'SCM pipeline', 'verbose_name_plural': 'SCM pipelines'},
        ),
        migrations.AlterModelOptions(
            name='scmrelease',
            options={'ordering': ['-created_at'], 'verbose_name': 'SCM release', 'verbose_name_plural': 'SCM releases'},
        ),
        migrations.AddIndex(
            model_name='scmpipelinerun',
            index=models.Index(fields=['-created_at'], name='katka_scmpi_created_7cc44e_idx'),
        ),
        migrations.AddIndex(
            model_name='scmrelease',
            index=models.Index(fields=['-created_at'], name='katka_scmre_created_b5704e_idx'),
        ),
    ]
