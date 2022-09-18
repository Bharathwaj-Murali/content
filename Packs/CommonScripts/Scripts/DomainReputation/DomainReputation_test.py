import demistomock as demisto  # noqa: F401
from CommonServerPython import *  # noqa: F401


def test_domain_reputation(mocker):
    """
    Given:
        - The script args.
    When:
        - Running ip_reputation function.
    Then:
        - Validating the outputs as expected.
    """
    from DomainReputation import domain_reputation
    mocker.patch.object(demisto, 'args', return_value={'ip': 'domain.com'})
    execute_command_res = [{'Type': 4, 'Contents': 'Error', 'Brand': 'brand'}]
    execute_mock = mocker.patch.object(demisto, 'executeCommand', return_value=execute_command_res)
    results_mock = mocker.patch.object(demisto, 'results')
    domain_reputation()
    assert execute_mock.call_count == 1
    assert 'returned an error' in results_mock.call_args[0][0][0]['Contents']
