import unittest

try:
    import packed_policy_replay_analysis as packed
except ModuleNotFoundError:  # pragma: no cover
    from quasar import packed_policy_replay_analysis as packed


class PackedPolicyReplayAnalysisTests(unittest.TestCase):
    def test_any_packing_delays_secret_physical_reset_when_payload_is_live(self) -> None:
        operations = [
            {
                "op": "append",
                "zone_id": 1,
                "group": 100,
                "blocks": 4,
                "intent": "KEM_ARTIFACT",
                "is_gc": False,
                "account_user": True,
            },
            {
                "op": "append",
                "zone_id": 2,
                "group": 200,
                "blocks": 4,
                "intent": "PAYLOAD",
                "is_gc": False,
                "account_user": True,
            },
            {"op": "reset_zone", "zone_id": 1, "group": 100},
        ]

        result = packed.analyze_operations(
            operations,
            physical_zone_count=8,
            physical_zone_capacity=16,
            packing="any",
        )

        self.assertFalse(result["failed"])
        self.assertEqual(result["logical_reset_commands"], 1)
        self.assertEqual(result["physical_reset_commands"], 0)
        self.assertEqual(result["delayed_logical_resets"], 1)
        self.assertEqual(result["secret_blocks_waiting_for_physical_reset"], 4)

    def test_group_packing_keeps_death_cohort_resettable(self) -> None:
        operations = [
            {
                "op": "append",
                "zone_id": 1,
                "group": 100,
                "blocks": 4,
                "intent": "KEM_ARTIFACT",
                "is_gc": False,
                "account_user": True,
            },
            {
                "op": "append",
                "zone_id": 2,
                "group": 200,
                "blocks": 4,
                "intent": "PAYLOAD",
                "is_gc": False,
                "account_user": True,
            },
            {"op": "reset_zone", "zone_id": 1, "group": 100},
        ]

        result = packed.analyze_operations(
            operations,
            physical_zone_count=8,
            physical_zone_capacity=16,
            packing="group",
        )

        self.assertFalse(result["failed"])
        self.assertEqual(result["logical_reset_commands"], 1)
        self.assertEqual(result["physical_reset_commands"], 1)
        self.assertEqual(result["delayed_logical_resets"], 0)
        self.assertEqual(result["secret_blocks_waiting_for_physical_reset"], 0)

    def test_logical_zone_packing_uses_one_pack_key_per_logical_zone(self) -> None:
        operations = [
            {
                "op": "append",
                "zone_id": 1,
                "group": 100,
                "blocks": 4,
                "intent": "KEM_ARTIFACT",
                "is_gc": False,
                "account_user": True,
            },
            {
                "op": "append",
                "zone_id": 2,
                "group": 100,
                "blocks": 4,
                "intent": "KEM_ARTIFACT",
                "is_gc": False,
                "account_user": True,
            },
        ]

        result = packed.analyze_operations(
            operations,
            physical_zone_count=8,
            physical_zone_capacity=16,
            packing="logical-zone",
        )

        self.assertFalse(result["failed"])
        self.assertEqual(result["max_live_physical_zones"], 2)
        self.assertEqual(result["max_active_pack_keys"], 2)

    def test_epoch_bin_packing_trades_reset_delay_for_fewer_physical_zones(self) -> None:
        operations = [
            {
                "op": "append",
                "zone_id": 1,
                "group": 100,
                "blocks": 4,
                "intent": "KEM_ARTIFACT",
                "epoch_id": 0,
                "is_gc": False,
                "account_user": True,
            },
            {
                "op": "append",
                "zone_id": 2,
                "group": 200,
                "blocks": 4,
                "intent": "KEM_ARTIFACT",
                "epoch_id": 1,
                "is_gc": False,
                "account_user": True,
            },
            {"op": "reset_zone", "zone_id": 1, "group": 100},
            {"op": "reset_zone", "zone_id": 2, "group": 200},
        ]

        result = packed.analyze_operations(
            operations,
            physical_zone_count=8,
            physical_zone_capacity=16,
            packing="epoch-bin-2",
        )

        self.assertFalse(result["failed"])
        self.assertEqual(result["max_live_physical_zones"], 1)
        self.assertEqual(result["physical_reset_commands"], 1)
        self.assertEqual(result["delayed_logical_resets"], 1)
        self.assertEqual(result["secret_blocks_waiting_for_physical_reset"], 0)
        self.assertEqual(result["max_secret_blocks_waiting_for_physical_reset"], 8)

    def test_secret_group_packing_keeps_secret_cohorts_and_packs_payload(self) -> None:
        operations = [
            {
                "op": "append",
                "zone_id": 1,
                "group": 100,
                "blocks": 4,
                "intent": "KEM_ARTIFACT",
                "epoch_id": 0,
                "is_gc": False,
                "account_user": True,
            },
            {
                "op": "append",
                "zone_id": 2,
                "group": 200,
                "blocks": 4,
                "intent": "KEM_ARTIFACT",
                "epoch_id": 1,
                "is_gc": False,
                "account_user": True,
            },
            {
                "op": "append",
                "zone_id": 3,
                "group": 300,
                "blocks": 4,
                "intent": "PAYLOAD",
                "epoch_id": 0,
                "is_gc": False,
                "account_user": True,
            },
            {
                "op": "append",
                "zone_id": 4,
                "group": 400,
                "blocks": 4,
                "intent": "PAYLOAD",
                "epoch_id": 1,
                "is_gc": False,
                "account_user": True,
            },
            {"op": "reset_zone", "zone_id": 1, "group": 100},
            {"op": "reset_zone", "zone_id": 2, "group": 200},
        ]

        result = packed.analyze_operations(
            operations,
            physical_zone_count=8,
            physical_zone_capacity=16,
            packing="secret-group",
        )

        self.assertFalse(result["failed"])
        self.assertEqual(result["max_live_physical_zones"], 3)
        self.assertEqual(result["physical_reset_commands"], 2)
        self.assertEqual(result["delayed_logical_resets"], 0)
        self.assertEqual(result["secret_blocks_waiting_for_physical_reset"], 0)


if __name__ == "__main__":
    unittest.main()
