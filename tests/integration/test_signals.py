from django.test import override_settings

import mock
import pytest
from katka import constants
from katka.fields import username_on_model
from katka.models import SCMPipelineRun, SCMRelease, SCMStepRun
from requests import HTTPError


@pytest.mark.django_db
class TestSCMStepsRunSignals:
    def test_steps_updated(self, scm_step_run, scm_pipeline_run):
        assert scm_pipeline_run.steps_total == 1
        assert scm_pipeline_run.steps_completed == 0
        assert scm_pipeline_run.modified_username == 'initial'
        assert scm_step_run.status == constants.STEP_STATUS_NOT_STARTED

        scm_step_run.status = constants.STEP_STATUS_SUCCESS
        with username_on_model(SCMStepRun, 'signal_tester'):
            scm_step_run.save()

        assert scm_pipeline_run.steps_total == 1
        assert scm_pipeline_run.steps_completed == 1
        assert scm_pipeline_run.modified_username == 'signal_tester'


@pytest.mark.django_db
class TestSCMPipelineRunSignals:
    def test_notify_post(self, scm_step_run, scm_pipeline_run):
        session = mock.MagicMock()
        overrides = {
            'PIPELINE_CHANGE_NOTIFICATION_SESSION': session,
            'PIPELINE_CHANGE_NOTIFICATION_URL': 'http://override-url/',
        }
        with override_settings(**overrides):
            with username_on_model(SCMPipelineRun, 'signal_tester'):
                scm_pipeline_run.status = constants.PIPELINE_STATUS_IN_PROGRESS
                scm_pipeline_run.save()

            with username_on_model(SCMStepRun, 'signal_tester'):
                scm_step_run.status = constants.STEP_STATUS_IN_PROGRESS
                scm_step_run.save()

                scm_step_run.status = constants.STEP_STATUS_FAILED
                scm_step_run.save()

            # should be called twice:
            # - once for the status update of the pipeline (from initializing to "in progress"), and
            # - once because the number of completed steps changed
            # but not a third time, because:
            # - the step status changed from non-final ("not started") to non-final ("in progress") so the
            #   number of completed steps in the pipeline did not change
            assert session.post.call_args_list == [
                mock.call('http://override-url/', json={'public_identifier': str(scm_pipeline_run.public_identifier)}),
                mock.call('http://override-url/', json={'public_identifier': str(scm_pipeline_run.public_identifier)}),
            ]

    def test_initializing(self, scm_step_run, scm_pipeline_run):
        session = mock.MagicMock()
        overrides = {
            'PIPELINE_CHANGE_NOTIFICATION_SESSION': session,
            'PIPELINE_CHANGE_NOTIFICATION_URL': 'http://override-url/',
        }
        with override_settings(**overrides):
            with username_on_model(SCMStepRun, 'signal_tester'):
                scm_step_run.status = constants.STEP_STATUS_IN_PROGRESS
                scm_step_run.save()

                scm_step_run.status = constants.STEP_STATUS_FAILED
                scm_step_run.save()

            # should not be called because the pipeline is still initializing
            assert session.post.call_args_list == []

    def test_send_on_create_pipeline(self, application, caplog):
        session = mock.MagicMock()
        overrides = {
            'PIPELINE_CHANGE_NOTIFICATION_SESSION': session,
            'PIPELINE_CHANGE_NOTIFICATION_URL': 'http://override-url/',
        }
        with override_settings(**overrides), username_on_model(SCMPipelineRun, 'signal_tester'):
            pipeline_run = SCMPipelineRun.objects.create(steps_total=0, application=application)

        # should not be called because the pipeline is still initializing
        assert session.post.call_args_list == [
            mock.call('http://override-url/', json={'public_identifier': str(pipeline_run.public_identifier)}),
        ]

        with override_settings(**overrides), username_on_model(SCMPipelineRun, 'signal_tester'):
            pipeline_run.steps_total = 1
            pipeline_run.save()

        assert len(session.post.call_args_list) == 1

        with override_settings(**overrides), username_on_model(SCMPipelineRun, 'signal_tester'):
            pipeline_run.status = constants.PIPELINE_STATUS_IN_PROGRESS
            pipeline_run.save()

        assert len(session.post.call_args_list) == 2

        assert 'Failed to notify pipeline runner' not in caplog.messages

    def test_send_on_create_pipeline_exception(self, application, caplog):
        session = mock.MagicMock()
        mock_response = mock.MagicMock()
        mock_response.raise_for_status.side_effect = HTTPError("Error", 404)
        session.post.return_value = mock_response
        overrides = {
            'PIPELINE_CHANGE_NOTIFICATION_SESSION': session,
            'PIPELINE_CHANGE_NOTIFICATION_URL': 'http://override-url/',
        }
        with override_settings(**overrides), username_on_model(SCMPipelineRun, 'signal_tester'):
            pipeline_run = SCMPipelineRun.objects.create(steps_total=0, application=application)

        # should not be called because the pipeline is still initializing
        assert session.post.call_args_list == [
            mock.call('http://override-url/', json={'public_identifier': str(pipeline_run.public_identifier)}),
        ]

        with override_settings(**overrides), username_on_model(SCMPipelineRun, 'signal_tester'):
            pipeline_run.steps_total = 1
            pipeline_run.save()

        assert len(session.post.call_args_list) == 1

        assert 'Failed to notify pipeline runner' in caplog.messages


@pytest.mark.django_db
class TestReleaseSignal:
    def test_release_created_when_pipeline_run_created(self, application):
        assert SCMRelease.objects.count() == 0

        session = mock.MagicMock()
        overrides = {'PIPELINE_CHANGE_NOTIFICATION_SESSION': session}
        with override_settings(**overrides), username_on_model(SCMPipelineRun, 'signal_tester'):
            pipeline_run = SCMPipelineRun.objects.create(application=application)

        assert SCMRelease.objects.count() == 1
        assert SCMRelease.objects.filter(scm_pipeline_runs__pk__exact=pipeline_run.pk).count() == 1

    def test_release_not_created_when_updating(self, scm_pipeline_run):
        session = mock.MagicMock()
        overrides = {'PIPELINE_CHANGE_NOTIFICATION_SESSION': session}

        # before
        assert SCMRelease.objects.count() == 1
        with override_settings(**overrides), username_on_model(SCMPipelineRun, 'signal_tester'):
            scm_pipeline_run.status = 'success'
            scm_pipeline_run.save()

        # after
        assert SCMRelease.objects.count() == 1

    def test_new_pipeline_gets_added_to_open_release(self, scm_pipeline_run, application):
        """When a release is still open, NO new release should be created when a new pipeline is created"""
        assert SCMRelease.objects.count() == 1

        session = mock.MagicMock()
        overrides = {'PIPELINE_CHANGE_NOTIFICATION_SESSION': session}
        with override_settings(**overrides), username_on_model(SCMPipelineRun, 'signal_tester'):
            pipeline_run = SCMPipelineRun.objects.create(application=application)

        assert SCMRelease.objects.count() == 1
        release = SCMRelease.objects.first()
        assert len(release.scm_pipeline_runs.all()) == 2
        assert release.scm_pipeline_runs.filter(pk__exact=scm_pipeline_run.pk).count() == 1
        assert release.scm_pipeline_runs.filter(pk__exact=pipeline_run.pk).count() == 1

    def test_new_pipeline_gets_added_to_new_release(self, scm_pipeline_run, scm_release, application):
        """When a release is closed, a new release should be created when a new pipeline is created"""
        assert SCMRelease.objects.count() == 1

        session = mock.MagicMock()
        overrides = {'PIPELINE_CHANGE_NOTIFICATION_SESSION': session}
        with override_settings(**overrides), username_on_model(SCMRelease, 'signal_tester'):
            scm_release.status = 'closed'
            scm_release.save()

        with override_settings(**overrides), username_on_model(SCMPipelineRun, 'signal_tester'):
            pipeline_run = SCMPipelineRun.objects.create(application=application)

        assert SCMRelease.objects.count() == 2
        release = SCMRelease.objects.filter(scm_pipeline_runs__pk__exact=pipeline_run.pk).first()
        assert release.pk != scm_release.pk

        assert len(scm_release.scm_pipeline_runs.all()) == 1
        assert scm_release.scm_pipeline_runs.filter(pk__exact=scm_pipeline_run.pk).count() == 1

        assert len(release.scm_pipeline_runs.all()) == 1
        assert release.scm_pipeline_runs.filter(pk__exact=pipeline_run.pk).count() == 1

    def test_multiple_applications(self, scm_pipeline_run, another_scm_pipeline_run, scm_release, another_scm_release):
        """Different releases should be created for pipeline_runs of different applications"""
        assert SCMRelease.objects.count() == 2
        assert another_scm_release.pk != scm_release.pk

        assert len(scm_release.scm_pipeline_runs.all()) == 1
        assert scm_release.scm_pipeline_runs.filter(pk__exact=scm_pipeline_run.pk).count() == 1

        assert len(another_scm_release.scm_pipeline_runs.all()) == 1
        assert another_scm_release.scm_pipeline_runs.filter(pk__exact=another_scm_pipeline_run.pk).count() == 1

    def test_pick_newest_on_duplicate_open_releases(self, application, scm_release, scm_pipeline_run, caplog):
        """This should not happen, but if it happens, handle it gracefully"""
        session = mock.MagicMock()
        overrides = {'PIPELINE_CHANGE_NOTIFICATION_SESSION': session}
        with override_settings(**overrides), username_on_model(SCMRelease, 'signal_tester'):
            open_release_2 = SCMRelease.objects.create()
            open_release_2.scm_pipeline_runs.add(scm_pipeline_run)
            open_release_2.save()

        assert scm_release.created_at < open_release_2.created_at

        with override_settings(**overrides), username_on_model(SCMPipelineRun, 'signal_tester'):
            pipeline_run = SCMPipelineRun.objects.create(application=application)

        assert SCMRelease.objects.count() == 2
        assert not scm_release.scm_pipeline_runs.filter(pk=pipeline_run.pk).exists()
        assert open_release_2.scm_pipeline_runs.filter(pk=pipeline_run.pk).exists()
        katka_records = [record.message for record in caplog.records if record.name == 'katka']
        assert len(katka_records) == 1
        assert 'Multiple open releases found' in katka_records[0]
        assert 'picking newest' in katka_records[0]
