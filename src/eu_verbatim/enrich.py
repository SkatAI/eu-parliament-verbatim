"""Speaker enrichment from the /meps and /corporate-bodies endpoints."""

from .client import ApiClient
from .codes import country, last_segment


def _active_on(membership: dict, date: str) -> bool:
    period = membership.get("memberDuring") or {}
    start, end = period.get("startDate"), period.get("endDate")
    return bool(start) and start <= date and (end is None or date <= end)


class SpeakerEnricher:
    def __init__(self, client: ApiClient):
        self.client = client
        self._orgs: dict[str, dict | None] = {}

    def organization(self, org_uri: str | None) -> dict | None:
        org_id = last_segment(org_uri)
        if not org_id:
            return None
        if org_id not in self._orgs:
            body = self.client.corporate_body(org_id)
            self._orgs[org_id] = (
                {
                    "id": org_id,
                    "label": body.get("label"),
                    "name": (body.get("altLabel") or {}).get("en") or body.get("label"),
                }
                if body
                else {"id": org_id, "label": None, "name": None}
            )
        return self._orgs[org_id]

    def _membership_org(self, memberships: list[dict], classification: str, date: str) -> dict | None:
        for m in memberships:
            if m.get("membershipClassification") == f"def/ep-entities/{classification}" and _active_on(m, date):
                return self.organization(m.get("organization"))
        return None

    def speaker(self, person_id: str | None, date: str, name_in_transcript: str | None) -> dict | None:
        if not person_id:
            return None
        mep = self.client.mep(person_id)
        if mep is None:
            # Not in the MEP database (e.g. a Commissioner or Council representative who was never an MEP).
            return {
                "person_id": person_id,
                "in_mep_database": False,
                "is_mep_on_date": False,
                "first_name": None,
                "last_name": None,
                "full_name": name_in_transcript,
                "nationality": None,
                "political_group": None,
                "national_party": None,
            }
        memberships = mep.get("hasMembership") or []
        mandate = next(
            (
                m for m in memberships
                if m.get("role") == "def/ep-roles/MEMBER_PARLIAMENT" and _active_on(m, date)
            ),
            None,
        )
        nationality = mep.get("citizenship") or ((mandate or {}).get("represents") or [None])[0]
        return {
            "person_id": person_id,
            "in_mep_database": True,
            "is_mep_on_date": mandate is not None,
            "first_name": mep.get("givenName"),
            "last_name": mep.get("familyName"),
            "full_name": " ".join(filter(None, [mep.get("givenName"), mep.get("familyName")])) or mep.get("label"),
            "gender": last_segment(mep.get("hasGender")),
            "nationality": country(nationality),
            "political_group": self._membership_org(memberships, "EU_POLITICAL_GROUP", date),
            "national_party": self._membership_org(memberships, "NATIONAL_POLITICAL_GROUP", date),
        }
