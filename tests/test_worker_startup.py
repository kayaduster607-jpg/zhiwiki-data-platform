"""Exercise parser startup failures through the real job state store."""

from types import SimpleNamespace
import time

import pytest

from test_team_service import team
from zhiwiki.service import worker
from zhiwiki.service.common import digest


def enqueue_job(team_state, source):
    client, services, ids = team_state
    context = services.auth.principal(client.cookies['zw_session'])
    queued = services.jobs.enqueue(context, ids['kb'], 'example.txt', digest(source), 'new', source)
    return services, context, queued['job_id']


@pytest.mark.parametrize('error_type', [FileNotFoundError, PermissionError])
def test_parser_start_failure_marks_job_failed_without_leaking_path(team, monkeypatch, caplog, error_type):
    services, context, job_id = enqueue_job(team, 'startup-once')

    def fail_start(*args, **kwargs):
        raise error_type('sensitive-interpreter-path')

    monkeypatch.setattr(worker.subprocess, 'Popen', fail_start)
    worker.supervise(services.settings, once=True)

    result = services.jobs.get(context, job_id)
    assert result['status'] == 'failed'
    assert result['error'] == 'IMPORT_PROCESS_START_FAILED'
    assert result['attempt'] == 1
    assert error_type.__name__ in caplog.text
    assert 'sensitive-interpreter-path' not in caplog.text


def test_parser_start_failure_backs_off_and_handles_another_job(team, monkeypatch):
    services, context, first = enqueue_job(team, 'startup-first')
    _, _, second = enqueue_job(team, 'startup-second')
    (services.db.root / 'uploads' / digest('startup-second')).write_text('startup-second', encoding='utf-8')
    sleep_delays, launches = [], []

    class StopLoop(Exception):
        pass

    def launch(command, **kwargs):
        launches.append(command)
        if len(launches) == 1:
            raise FileNotFoundError('sensitive-interpreter-path')
        # Run the second job synchronously to verify supervision resumes.
        worker.process_job(services.settings, command[-2], int(command[-1]))
        return SimpleNamespace(poll=lambda: 0, returncode=0)

    def stop_on_sleep(delay):
        sleep_delays.append(delay)
        if len(sleep_delays) == 2:
            raise StopLoop()

    monkeypatch.setattr(worker.subprocess, 'Popen', launch)
    monkeypatch.setattr(worker, 'time', SimpleNamespace(monotonic=time.monotonic, time=time.time, sleep=stop_on_sleep))
    with pytest.raises(StopLoop):
        worker.supervise(services.settings)

    assert services.jobs.get(context, first)['status'] == 'failed'
    assert services.jobs.get(context, second)['status'] in ('awaiting_publish', 'needs_review')
    assert sleep_delays == [0.5, 0.5]
    assert len(launches) == 2
