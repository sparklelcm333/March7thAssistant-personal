from app.tools.check_update import UpdateStatus


class TestUpdateStatus:
    def test_success_value(self):
        assert UpdateStatus.SUCCESS.value == 1

    def test_update_available_value(self):
        assert UpdateStatus.UPDATE_AVAILABLE.value == 2

    def test_failure_value(self):
        assert UpdateStatus.FAILURE.value == 0

    def test_all_members(self):
        assert len(UpdateStatus) == 3
