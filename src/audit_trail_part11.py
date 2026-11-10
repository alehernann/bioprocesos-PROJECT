"""Tamper-evident audit-trail logger for 21 CFR Part 11 / EU GMP Annex 22.

Implements a hash-chained (blockchain-style) audit trail for electronic records,
satisfying the electronic-record integrity requirements of 21 CFR Part 11 and the
human-in-the-loop guardrail of the EU GMP EudraLex Vol. 4 Draft Annex 22 (Artificial
Intelligence). Each record links to the SHA-256 hash of the previous record, so any
later alteration breaks the chain and is detectable by :meth:`verify_chain_integrity`.
"""

import datetime
import hashlib


class AuditTrailLogger:
    """Hash-chained, tamper-evident audit-trail logger.

    Records are stored in :attr:`records` as dicts. Each record carries the
    previous record's hash (``prev_hash``), a UTC ISO 8601 timestamp, the change
    metadata, and its own SHA-256 ``sha256_hash`` computed over the chained fields.
    """

    def __init__(self):
        self.records: list[dict] = []

    def append_record(
        self,
        user_id,
        role,
        parameter_name,
        old_value,
        new_value,
        reason_for_change,
        human_approved: bool = True,
    ) -> dict:
        """Append a new, hash-chained audit record and return it.

        Enforces the Annex 22 human-in-the-loop guardrail (no AI/digital-twin
        parameter change without explicit human approval) and the Part 11
        requirement for a documented reason for change.
        """
        if not human_approved:
            raise PermissionError(
                "EU GMP Annex 22 / 21 CFR Part 11 Violation: AI/Digital Twin "
                "parameter change requires explicit human-in-the-loop approval."
            )
        if len(reason_for_change.strip()) < 5:
            raise ValueError(
                "21 CFR Part 11 requires a valid engineering reason for change."
            )

        prev_hash = (
            self.records[-1]["sha256_hash"]
            if self.records
            else "GENESIS_BLOCK_0000000000000000"
        )
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # human_approved is part of the hashed payload, so flipping the approval
        # flag after the fact is detected by verify_chain_integrity().
        sha256_hash = hashlib.sha256(
            f"{prev_hash}|{timestamp}|{user_id}|{role}|{parameter_name}|"
            f"{old_value}|{new_value}|{reason_for_change}|"
            f"{bool(human_approved)}".encode("utf-8")
        ).hexdigest()

        record = {
            "prev_hash": prev_hash,
            "timestamp": timestamp,
            "user_id": user_id,
            "role": role,
            "parameter_name": parameter_name,
            "old_value": old_value,
            "new_value": new_value,
            "reason_for_change": reason_for_change,
            "human_approved": human_approved,
            "sha256_hash": sha256_hash,
        }
        self.records.append(record)
        return record

    def verify_chain_integrity(self) -> bool:
        """Recompute the hash chain from the genesis block and verify integrity.

        Returns ``True`` if every record's ``prev_hash`` links correctly and every
        stored ``sha256_hash`` matches the recomputed value; ``False`` if any
        record (or its ordering) has been altered.

        The hashed payload ends with ``|{bool(human_approved)}`` (v1.2.0). Chains
        hashed with the earlier payload (without that field) do not verify.
        """
        expected_prev = "GENESIS_BLOCK_0000000000000000"
        for record in self.records:
            if record["prev_hash"] != expected_prev:
                return False
            recomputed = hashlib.sha256(
                f"{record['prev_hash']}|{record['timestamp']}|{record['user_id']}|"
                f"{record['role']}|{record['parameter_name']}|{record['old_value']}|"
                f"{record['new_value']}|{record['reason_for_change']}|"
                f"{bool(record['human_approved'])}".encode("utf-8")
            ).hexdigest()
            if recomputed != record["sha256_hash"]:
                return False
            expected_prev = record["sha256_hash"]
        return True
