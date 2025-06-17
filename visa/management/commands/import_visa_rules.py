import csv, json, sys
from pathlib import Path
from typing import Iterable
from re import fullmatch

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from visa.models import VisaRequirement

# ------------------------------------------------------------------
# Smarter parser: returns (visa_enum, notes)
# ------------------------------------------------------------------
def parse_requirement(raw: str):
    text = (raw or "").strip().lower()

    # 1. numeric → visa-free N days
    if fullmatch(r"\d{1,3}", text):
        return (
            VisaRequirement.VisaType.NONE,
            f"Visa free for {text} days",
        )

    # 2. free-entry variants
    if text in {
        "visa free", "visa_free", "visa free entry", "visa_free_entry",
        "no visa", "no_visa", "no visa needed",
    }:
        return (VisaRequirement.VisaType.NONE, "No visa needed")

    # 3. no admission
    if text == "no admission":
        return (
            VisaRequirement.VisaType.VISA,
            "Visa needed (no admission without visa)",
        )

    # 4. standard labels
    STANDARD = {
        "visa_required":       VisaRequirement.VisaType.VISA,
        "visa required":       VisaRequirement.VisaType.VISA,
        "visa-required":       VisaRequirement.VisaType.VISA,
        "e_visa":              VisaRequirement.VisaType.EVISA,
        "e-visa":              VisaRequirement.VisaType.EVISA,
        "eta":                 VisaRequirement.VisaType.EVISA,
        "visa_on_arrival":     VisaRequirement.VisaType.VOA,
        "visa on arrival":     VisaRequirement.VisaType.VOA,
        "other":               VisaRequirement.VisaType.OTHER,
        "unknown":             VisaRequirement.VisaType.OTHER,
    }
    if text in STANDARD:
        return (STANDARD[text], "")

    # 5. fallback
    return (VisaRequirement.VisaType.OTHER, text or "")

# ------- helper: load CSV or JSON -------------------------------------
def load_rows(path: Path) -> Iterable[dict]:
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                yield row
    elif path.suffix.lower() == ".json":
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise CommandError("JSON root must be a list of objects")
        for row in data:
            yield row
    else:
        raise CommandError("File must be .csv or .json")

# ------- management command ------------------------------------------
class Command(BaseCommand):
    help = "Bulk-import visa rules from CSV or JSON into VisaRequirement"

    def add_arguments(self, parser):
        parser.add_argument("file", type=str, help="Path to CSV or JSON")
        parser.add_argument("--dry-run", action="store_true",
                            help="Validate only; no database writes")
        parser.add_argument("--truncate", action="store_true",
                            help="Empty VisaRequirement table before import")

    @transaction.atomic
    def handle(self, *args, **opts):
        path = Path(opts["file"]).expanduser()
        if not path.exists():
            raise CommandError(f"{path} not found")

        if opts["truncate"] and not opts["dry_run"]:
            count, _ = VisaRequirement.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Truncated {count} rows"))

        created = updated = errors = 0
        for idx, row in enumerate(load_rows(path), start=1):
            try:
                document_country = (
                    row.get("document_country")
                    or row.get("passport_country")
                    or row.get("passport")
                    or row.get("Passport")
                )
                destination_country = (
                    row.get("destination_country")
                    or row.get("destination")
                    or row.get("Destination")
                )
                p, d = document_country.strip().upper(), destination_country.strip().upper()
                visa_enum, extra_notes = parse_requirement(
                    row.get("visa_type")
                    or row.get("requirement")
                    or row.get("Requirement", "")
                )
                notes = (
                    extra_notes
                    or row.get("notes", "")
                )

                if opts["dry_run"]:
                    continue  # just count
                obj, was_created = VisaRequirement.objects.update_or_create(
                    document_country=p,
                    destination_country=d,
                    defaults=dict(visa_type=visa_enum, notes=notes),
                )
                created += int(was_created)
                updated += int(not was_created)
            except Exception as exc:  # broad for robustness
                errors += 1
                self.stderr.write(
                    self.style.ERROR(f"Row {idx}: {exc} → {row}")
                )

        # -- summary ---------------------------------------------------
        if opts["dry_run"]:
            self.stdout.write(self.style.NOTICE("Dry-run complete"))
        self.stdout.write(
            self.style.SUCCESS(f"✔ created {created}   ✏ updated {updated}")
        )
        if errors:
            self.stdout.write(
                self.style.ERROR(f"⚠ {errors} rows had errors (see above)")
            ) 