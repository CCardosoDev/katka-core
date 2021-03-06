from uuid import UUID

from django.utils.dateparse import parse_datetime

import pytest
from freezegun import freeze_time
from katka import models


@pytest.mark.django_db
class TestSCMStepRunViewSetUnauthenticated:
    """
    When a user is not logged in, no group information is available, so nothing is returned.

    For listing, that would be an empty list for other operations, an error like the object could
    not be found, except on create (you need to be part of a group and anonymous users do not have any)
    """

    def test_list(self, client, scm_step_run):
        response = client.get('/scm-step-runs/')
        assert response.status_code == 200
        parsed = response.json()
        assert len(parsed) == 0

    def test_get(self, client, scm_step_run):
        response = client.get(f'/scm-step-runs/{scm_step_run.public_identifier}/')
        assert response.status_code == 404

    def test_delete(self, client, scm_step_run):
        response = client.delete(f'/scm-step-runs/{scm_step_run.public_identifier}/')
        assert response.status_code == 404

    def test_update(self, client, scm_pipeline_run, scm_step_run):
        url = f'/scm-step-runs/{scm_step_run.public_identifier}/'
        data = {'slug': 'release',
                'name': 'Release product',
                'stage': 'Production',
                'status': 'success',
                'output': 'Command completed',
                'scm_pipeline_run': scm_pipeline_run.public_identifier}
        response = client.put(url, data, content_type='application/json')
        assert response.status_code == 404

    def test_partial_update(self, client, scm_step_run):
        url = f'/scm-step-runs/{scm_step_run.public_identifier}/'
        data = {'output': 'Step executed.'}
        response = client.patch(url, data, content_type='application/json')
        assert response.status_code == 404

    def test_create(self, client, scm_pipeline_run, scm_step_run):
        url = f'/scm-step-runs/'
        data = {'slug': 'release',
                'name': 'Release product',
                'stage': 'Production',
                'status': 'in progress',
                'scm_pipeline_run': scm_pipeline_run.public_identifier}
        response = client.post(url, data=data, content_type='application/json')
        assert response.status_code == 403


@pytest.mark.django_db
class TestSCMStepRunViewSet:

    def test_list(self, client, logged_in_user, scm_pipeline_run, scm_step_run):
        response = client.get('/scm-step-runs/')
        assert response.status_code == 200
        parsed = response.json()
        assert len(parsed) == 1
        assert parsed[0]['slug'] == 'release'
        assert parsed[0]['name'] == 'Release Katka'
        assert parsed[0]['stage'] == 'Production'
        assert parsed[0]['status'] == 'not started'
        assert parsed[0]['output'] == ''
        assert parsed[0]['started_at'] == '2018-11-11T08:25:30Z'
        assert parsed[0]['ended_at'] == '2018-11-11T09:01:40Z'
        assert UUID(parsed[0]['scm_pipeline_run']) == scm_pipeline_run.public_identifier
        UUID(parsed[0]['public_identifier'])  # should not raise

    def test_filtered_list(self, client, logged_in_user, scm_pipeline_run, scm_step_run,
                           another_scm_pipeline_run, another_scm_step_run):

        response = client.get('/scm-step-runs/?scm_pipeline_run=' + str(another_scm_pipeline_run.public_identifier))
        assert response.status_code == 200
        parsed = response.json()
        assert len(parsed) == 1
        assert parsed[0]['slug'] == 'another-release'
        assert parsed[0]['name'] == 'Another Release Katka'
        assert parsed[0]['stage'] == 'Production'
        assert parsed[0]['status'] == 'not started'
        assert parsed[0]['output'] == ''
        assert parsed[0]['started_at'] is None
        assert parsed[0]['ended_at'] is None
        assert UUID(parsed[0]['scm_pipeline_run']) == another_scm_pipeline_run.public_identifier
        UUID(parsed[0]['public_identifier'])  # should not raise

    def test_filtered_list_non_existing_pipeline_run(self, client, logged_in_user, scm_pipeline_run, scm_step_run,
                                                     another_scm_pipeline_run, another_scm_step_run):

        response = client.get('/scm-step-runs/?scm_pipeline_run=12345678-1234-5678-1234-567812345678')
        assert response.status_code == 200
        parsed = response.json()
        assert len(parsed) == 0

    def test_list_excludes_inactive(self, client, logged_in_user, deactivated_scm_step_run):
        response = client.get('/scm-step-runs/')
        assert response.status_code == 200
        parsed = response.json()
        assert len(parsed) == 0

    def test_get(self, client, logged_in_user, scm_pipeline_run, scm_step_run):
        response = client.get(f'/scm-step-runs/{scm_step_run.public_identifier}/')
        assert response.status_code == 200
        parsed = response.json()
        assert parsed['slug'] == 'release'
        assert parsed['name'] == 'Release Katka'
        assert parsed['stage'] == 'Production'
        assert parsed['status'] == 'not started'
        assert parsed['output'] == ''
        assert parsed['step_type'] == 'type'
        assert parsed['sequence_id'] == '1.1-1'
        assert parsed['tags'] == ''
        assert parsed['started_at'] == '2018-11-11T08:25:30Z'
        assert parsed['ended_at'] == '2018-11-11T09:01:40Z'
        assert UUID(parsed['scm_pipeline_run']) == scm_pipeline_run.public_identifier
        UUID(parsed['public_identifier'])  # should not raise

    def test_get_excludes_inactive(self, client, logged_in_user, deactivated_scm_step_run):
        response = client.get(f'/scm-step-runs/{deactivated_scm_step_run.public_identifier}/')
        assert response.status_code == 404

    def test_delete(self, client, logged_in_user, scm_step_run):
        response = client.delete(f'/scm-step-runs/{scm_step_run.public_identifier}/')
        assert response.status_code == 204
        p = models.SCMStepRun.objects.get(pk=scm_step_run.public_identifier)
        assert p.deleted is True

    def test_update(self, client, logged_in_user, scm_pipeline_run, scm_step_run):
        url = f'/scm-step-runs/{scm_step_run.public_identifier}/'
        data = {'slug': 'release',
                'name': 'Release product',
                'stage': 'Production',
                'status': 'success',
                'step_type': 'type1',
                'output': 'Command completed',
                'sequence_id': '01.02-03',
                'tags': 'tag1 tag2',
                'started_at': '2019-01-25 01:02:03+0100',
                'ended_at': '2019-02-13 02:03:04Z',
                'scm_pipeline_run': scm_pipeline_run.public_identifier}
        response = client.put(url, data, content_type='application/json')
        assert response.status_code == 200
        p = models.SCMStepRun.objects.get(pk=scm_step_run.public_identifier)
        assert p.name == 'Release product'
        assert p.sequence_id == '01.02-03'
        assert p.tags == 'tag1 tag2'
        assert p.step_type == 'type1'
        assert p.started_at == parse_datetime('2019-01-25T01:02:03+0100')
        assert p.ended_at == parse_datetime('2019-02-13T02:03:04Z')

    def test_partial_update(self, client, logged_in_user, scm_step_run):
        url = f'/scm-step-runs/{scm_step_run.public_identifier}/'
        data = {'output': 'Step executed.',
                'started_at': '2019-01-25 01:02:03+0200',
                'ended_at': '2019-02-13 02:03:04Z'}
        response = client.patch(url, data, content_type='application/json')
        assert response.status_code == 200
        p = models.SCMStepRun.objects.get(pk=scm_step_run.public_identifier)
        assert p.output == 'Step executed.'
        assert p.started_at == parse_datetime('2019-01-25T02:02:03+0300')
        assert p.ended_at == parse_datetime('2019-02-13T02:03:04Z')

    def test_partial_update_sets_ended(self, client, logged_in_user, another_scm_step_run):
        url = f'/scm-step-runs/{another_scm_step_run.public_identifier}/'
        data = {'status': 'success'}

        p = models.SCMStepRun.objects.get(pk=another_scm_step_run.public_identifier)
        assert p.ended_at is None

        with freeze_time("2019-05-04 11:13:14"):
            response = client.patch(url, data, content_type='application/json')

        assert response.status_code == 200
        p = models.SCMStepRun.objects.get(pk=another_scm_step_run.public_identifier)
        assert p.ended_at == parse_datetime('2019-05-04T11:13:14+0000')

    def test_create(self, client, logged_in_user, scm_pipeline_run, scm_step_run):
        initial_count = models.SCMStepRun.objects.count()
        url = f'/scm-step-runs/'
        data = {'slug': 'release',
                'name': 'Release product',
                'step_type': 'type1',
                'stage': 'Production',
                'status': 'not started',
                'scm_pipeline_run': scm_pipeline_run.public_identifier}
        response = client.post(url, data=data, content_type='application/json')
        assert response.status_code == 201
        assert models.SCMStepRun.objects.filter(name='Release product').exists()
        assert models.SCMStepRun.objects.count() == initial_count + 1
