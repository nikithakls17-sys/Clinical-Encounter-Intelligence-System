"""Small curated knowledge tables used by the rules. Not exhaustive; not for clinical use."""

# Generic name -> therapeutic group used for duplicate-therapy checks.
# Only groups where taking two members at once is usually unintended are listed.
DUPLICATE_GROUPS: dict[str, str] = {
    **dict.fromkeys(["ibuprofen", "naproxen", "diclofenac", "meloxicam", "celecoxib", "ketorolac", "indomethacin"], "NSAID"),
    **dict.fromkeys(["sertraline", "fluoxetine", "citalopram", "escitalopram", "paroxetine"], "SSRI"),
    **dict.fromkeys(["simvastatin", "atorvastatin", "rosuvastatin", "pravastatin", "lovastatin"], "statin"),
    **dict.fromkeys(["lisinopril", "enalapril", "ramipril", "benazepril", "losartan", "valsartan", "olmesartan"],
                    "RAAS blocker (ACE inhibitor / ARB)"),
    **dict.fromkeys(["omeprazole", "pantoprazole", "esomeprazole", "lansoprazole"], "proton pump inhibitor"),
    **dict.fromkeys(["warfarin", "apixaban", "rivaroxaban", "dabigatran", "enoxaparin"], "anticoagulant"),
    **dict.fromkeys(["alprazolam", "lorazepam", "clonazepam", "diazepam"], "benzodiazepine"),
}

# Allergy substance (lowercase) -> drugs that should trigger an allergy conflict.
ALLERGY_CROSS_REACTIVITY: dict[str, set[str]] = {
    "penicillin": {"penicillin", "amoxicillin", "ampicillin", "amoxicillin-clavulanate", "dicloxacillin",
                   "piperacillin", "nafcillin"},
    "sulfa drugs": {"sulfamethoxazole", "sulfamethoxazole-trimethoprim", "sulfasalazine", "sulfadiazine"},
    "codeine": {"codeine"},
    "iodinated contrast": {"iodinated contrast", "iohexol", "iopamidol"},
}


def allergy_matches(substance: str, drug: str) -> bool:
    substance = substance.lower().strip()
    return drug == substance or drug in ALLERGY_CROSS_REACTIVITY.get(substance, set())
