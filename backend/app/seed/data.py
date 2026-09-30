"""Synthetic seed data. Names, MRNs and notes are invented; any resemblance to real people is coincidental.

Dates are offsets in days relative to the day the seed runs (negative = past), so demo scenarios such as
"missed follow-up" stay current whenever the database is reseeded.

Several encounters are built to trigger specific anomaly rules later (stage 4):
  - warfarin + ibuprofen                       -> med_interaction (high)
  - sertraline + tramadol                      -> med_interaction (high)
  - lisinopril + spironolactone                -> med_interaction (moderate)
  - simvastatin + clarithromycin               -> med_interaction (high)
  - penicillin allergy + amoxicillin           -> allergy_conflict
  - naproxen + ibuprofen                       -> duplicate_therapy
  - overdue, uncompleted follow-ups            -> missed_follow_up
"""

PROVIDERS = [
    {"name": "Dr. Maya Okafor", "specialty": "Internal Medicine", "email": "m.okafor@example.org"},
    {"name": "Dr. Daniel Reyes", "specialty": "Family Medicine", "email": "d.reyes@example.org"},
    {"name": "Dr. Priya Raman", "specialty": "Cardiology", "email": "p.raman@example.org"},
    {"name": "Dr. Samuel Brooks", "specialty": "Psychiatry", "email": "s.brooks@example.org"},
]

# date_of_birth is ISO; allergies are (substance, reaction)
PATIENTS = [
    {"mrn": "CEIS-1001", "first_name": "Harold", "last_name": "Vance", "date_of_birth": "1951-03-14", "sex": "M",
     "allergies": [("sulfa drugs", "rash")]},
    {"mrn": "CEIS-1002", "first_name": "Linda", "last_name": "Marsh", "date_of_birth": "1978-07-02", "sex": "F",
     "allergies": []},
    {"mrn": "CEIS-1003", "first_name": "George", "last_name": "Albright", "date_of_birth": "1960-11-23", "sex": "M",
     "allergies": []},
    {"mrn": "CEIS-1004", "first_name": "Rosa", "last_name": "Delgado", "date_of_birth": "1969-01-30", "sex": "F",
     "allergies": [("codeine", "nausea and vomiting")]},
    {"mrn": "CEIS-1005", "first_name": "Kevin", "last_name": "Tran", "date_of_birth": "1992-09-18", "sex": "M",
     "allergies": [("penicillin", "hives and throat tightness")]},
    {"mrn": "CEIS-1006", "first_name": "Aisha", "last_name": "Bello", "date_of_birth": "1985-05-06", "sex": "F",
     "allergies": []},
    {"mrn": "CEIS-1007", "first_name": "Walter", "last_name": "Kim", "date_of_birth": "1947-12-01", "sex": "M",
     "allergies": [("latex", "contact dermatitis")]},
    {"mrn": "CEIS-1008", "first_name": "Emily", "last_name": "Novak", "date_of_birth": "2001-02-27", "sex": "F",
     "allergies": []},
    {"mrn": "CEIS-1009", "first_name": "Marcus", "last_name": "Hale", "date_of_birth": "1973-08-09", "sex": "M",
     "allergies": []},
    {"mrn": "CEIS-1010", "first_name": "Grace", "last_name": "Osei", "date_of_birth": "1958-04-15", "sex": "F",
     "allergies": [("iodinated contrast", "urticaria")]},
]

# Standing medication lists, i.e. what the EHR already knows before any note is processed.
# (mrn, name, drug_class, dose, frequency, start_offset_days)
MEDICATIONS = [
    ("CEIS-1001", "warfarin", "anticoagulant", "5 mg", "daily", -900),
    ("CEIS-1001", "metoprolol", "beta blocker", "25 mg", "twice daily", -900),
    ("CEIS-1002", "sertraline", "SSRI", "100 mg", "daily", -400),
    ("CEIS-1003", "lisinopril", "ACE inhibitor", "20 mg", "daily", -1200),
    ("CEIS-1003", "furosemide", "loop diuretic", "40 mg", "daily", -300),
    ("CEIS-1004", "simvastatin", "statin", "40 mg", "nightly", -700),
    ("CEIS-1004", "metformin", "biguanide", "1000 mg", "twice daily", -700),
    ("CEIS-1006", "levothyroxine", "thyroid hormone", "75 mcg", "daily", -500),
    ("CEIS-1007", "naproxen", "NSAID", "500 mg", "twice daily", -200),
    ("CEIS-1007", "amlodipine", "calcium channel blocker", "10 mg", "daily", -1500),
    ("CEIS-1009", "atorvastatin", "statin", "20 mg", "daily", -600),
    ("CEIS-1010", "metformin", "biguanide", "500 mg", "twice daily", -1000),
    ("CEIS-1010", "insulin glargine", "long-acting insulin", "18 units", "nightly", -250),
]

# follow_ups: (description, due_offset_days, completed)
ENCOUNTERS = [
    {
        "mrn": "CEIS-1001", "provider": "d.reyes@example.org", "offset": -12, "type": "office visit",
        "chief_complaint": "Right knee pain",
        "note": (
            "S: 75yo M with hx of atrial fibrillation on warfarin 5 mg daily presents with 2 weeks of right knee "
            "pain and swelling after gardening. Denies fever or trauma. Reports mild stiffness in the morning.\n"
            "O: BP 138/82, HR 74 irregular. R knee with small effusion, crepitus, full ROM. INR last month 2.6.\n"
            "A: Osteoarthritis of right knee (M17.11). Atrial fibrillation, rate controlled (I48.91).\n"
            "P: Start ibuprofen 400 mg three times daily with food for 10 days. Ice and activity modification. "
            "Continue warfarin and metoprolol 25 mg BID. Recheck INR in 1 week."
        ),
        "follow_ups": [("Recheck INR", -5, False)],
    },
    {
        "mrn": "CEIS-1002", "provider": "s.brooks@example.org", "offset": -30, "type": "telehealth",
        "chief_complaint": "Depression follow-up, back pain",
        "note": (
            "S: 48yo F with major depressive disorder on sertraline 100 mg daily reports improved mood, sleeping "
            "7 hours. New complaint of low back pain after moving furniture, 6/10, no radicular symptoms.\n"
            "O: Alert, euthymic, linear thought process. PHQ-9 score 6 (down from 14).\n"
            "A: Major depressive disorder, single episode, moderate, improving (F32.1). Acute low back pain (M54.50).\n"
            "P: Continue sertraline 100 mg daily. Tramadol 50 mg every 6 hours as needed for back pain, max 5 days. "
            "Follow up in 4 weeks."
        ),
        "follow_ups": [("Psychiatry follow-up visit", -2, False)],
    },
    {
        "mrn": "CEIS-1003", "provider": "p.raman@example.org", "offset": -20, "type": "office visit",
        "chief_complaint": "Shortness of breath and ankle swelling",
        "note": (
            "S: 65yo M with heart failure with reduced ejection fraction reports worsening dyspnea on exertion "
            "(1 flight of stairs) and bilateral ankle swelling for 3 weeks. Sleeps on 2 pillows. On lisinopril 20 mg "
            "and furosemide 40 mg daily.\n"
            "O: BP 124/76, HR 88, SpO2 95% RA. JVP elevated, bibasilar crackles, 2+ pitting edema bilaterally. "
            "EF 30% on echo 3 months ago. K 4.9.\n"
            "A: Chronic systolic heart failure, exacerbation (I50.22). Essential hypertension (I10).\n"
            "P: Add spironolactone 25 mg daily. Continue lisinopril and furosemide. BMP in 1 week to check "
            "potassium and creatinine. Daily weights, 2 g sodium diet."
        ),
        "follow_ups": [("BMP (potassium, creatinine)", -13, False), ("Cardiology follow-up", 10, False)],
    },
    {
        "mrn": "CEIS-1004", "provider": "m.okafor@example.org", "offset": -8, "type": "office visit",
        "chief_complaint": "Cough and fever",
        "note": (
            "S: 57yo F with type 2 diabetes and hyperlipidemia presents with 5 days of productive cough, fever to "
            "101.2F, and pleuritic chest pain on the right. On simvastatin 40 mg nightly and metformin 1000 mg BID.\n"
            "O: T 100.8F, RR 22, SpO2 93% RA. Crackles right lower lobe. CXR: RLL consolidation.\n"
            "A: Community-acquired pneumonia, RLL (J18.9). Type 2 diabetes mellitus without complications (E11.9). "
            "Hyperlipidemia (E78.5).\n"
            "P: Clarithromycin 500 mg twice daily for 7 days. Continue simvastatin and metformin. Return if "
            "worsening dyspnea. Recheck in clinic in 1 week."
        ),
        "follow_ups": [("Pneumonia recheck visit", -1, False)],
    },
    {
        "mrn": "CEIS-1005", "provider": "d.reyes@example.org", "offset": -3, "type": "urgent care",
        "chief_complaint": "Sore throat",
        "note": (
            "S: 34yo M with 3 days of sore throat, fever, and painful swallowing. No cough. Reports allergy to "
            "penicillin (hives).\n"
            "O: T 101.4F. Tonsillar exudates bilaterally, tender anterior cervical nodes. Rapid strep positive.\n"
            "A: Streptococcal pharyngitis (J02.0).\n"
            "P: Amoxicillin 500 mg twice daily for 10 days. Acetaminophen as needed. Return if unable to swallow."
        ),
        "follow_ups": [],
    },
    {
        "mrn": "CEIS-1006", "provider": "m.okafor@example.org", "offset": -45, "type": "office visit",
        "chief_complaint": "Fatigue",
        "note": (
            "S: 41yo F with hypothyroidism on levothyroxine 75 mcg daily reports 2 months of fatigue, cold "
            "intolerance, and 3 kg weight gain. Adherent to medication, takes it with coffee.\n"
            "O: BP 118/74, HR 62. Dry skin, delayed relaxation of reflexes. TSH 7.8 (high).\n"
            "A: Hypothyroidism, undertreated (E03.9).\n"
            "P: Increase levothyroxine to 88 mcg daily, take on empty stomach 30 minutes before coffee. Repeat TSH "
            "in 6 weeks."
        ),
        "follow_ups": [("Repeat TSH", -3, False)],
    },
    {
        "mrn": "CEIS-1007", "provider": "d.reyes@example.org", "offset": -6, "type": "office visit",
        "chief_complaint": "Hip pain",
        "note": (
            "S: 78yo M with hypertension and osteoarthritis on naproxen 500 mg BID and amlodipine 10 mg daily. "
            "Reports worsening left hip pain, says naproxen 'is not doing enough'.\n"
            "O: BP 146/88. Antalgic gait, pain with internal rotation of L hip. Cr 1.3 (baseline 1.1).\n"
            "A: Primary osteoarthritis, left hip (M16.12). Essential hypertension (I10).\n"
            "P: Add ibuprofen 600 mg three times daily as needed. Refer to physical therapy. Hip X-ray ordered."
        ),
        "follow_ups": [("Hip X-ray", 7, False), ("Physical therapy intake", 14, False)],
    },
    {
        "mrn": "CEIS-1008", "provider": "m.okafor@example.org", "offset": -15, "type": "office visit",
        "chief_complaint": "Headaches",
        "note": (
            "S: 25yo F with 3 months of bilateral pressing headaches, 3 to 4 per week, worse late in the day and with "
            "screen use. No aura, nausea, or neurologic symptoms. Uses acetaminophen 2 to 3 days per week.\n"
            "O: BP 112/70. Normal neurologic exam. Pericranial muscle tenderness.\n"
            "A: Tension-type headache, episodic (G44.209).\n"
            "P: Headache diary, sleep hygiene, limit acetaminophen to under 10 days per month. Follow up in 8 weeks."
        ),
        "follow_ups": [("Headache follow-up visit", 41, False)],
    },
    {
        "mrn": "CEIS-1009", "provider": "p.raman@example.org", "offset": -60, "type": "office visit",
        "chief_complaint": "Chest pain on exertion",
        "note": (
            "S: 53yo M with hyperlipidemia on atorvastatin 20 mg reports 4 weeks of substernal chest pressure with "
            "brisk walking, relieved by rest in 5 minutes. Smoker, 20 pack-years.\n"
            "O: BP 142/90, HR 78. Normal heart sounds. ECG: normal sinus rhythm, no acute changes. LDL 142.\n"
            "A: Stable angina (I20.8). Hyperlipidemia (E78.5). Nicotine dependence, cigarettes (F17.210).\n"
            "P: Aspirin 81 mg daily. Increase atorvastatin to 80 mg daily. Nitroglycerin 0.4 mg SL as needed. "
            "Exercise stress test within 2 weeks. Smoking cessation counseling provided."
        ),
        "follow_ups": [("Exercise stress test", -46, False), ("Lipid panel", -15, True)],
    },
    {
        "mrn": "CEIS-1010", "provider": "m.okafor@example.org", "offset": -95, "type": "office visit",
        "chief_complaint": "Diabetes check",
        "note": (
            "S: 68yo F with type 2 diabetes on metformin 500 mg BID and insulin glargine 18 units nightly. Fasting "
            "sugars 150 to 190. Reports tingling in both feet at night.\n"
            "O: BP 134/80. BMI 31. Decreased monofilament sensation both feet. HbA1c 8.6%.\n"
            "A: Type 2 diabetes with diabetic polyneuropathy (E11.42). Obesity (E66.9).\n"
            "P: Increase glargine to 22 units nightly. Increase metformin to 1000 mg BID. Refer to podiatry. "
            "Repeat HbA1c in 3 months. Annual diabetic eye exam."
        ),
        "follow_ups": [("Repeat HbA1c", -5, False), ("Diabetic eye exam", -35, False), ("Podiatry referral", -60, True)],
    },
    {
        "mrn": "CEIS-1001", "provider": "p.raman@example.org", "offset": -120, "type": "office visit",
        "chief_complaint": "Atrial fibrillation follow-up",
        "note": (
            "S: 75yo M with permanent atrial fibrillation, no palpitations, dyspnea, or bleeding. Adherent to "
            "warfarin 5 mg daily and metoprolol 25 mg BID.\n"
            "O: BP 130/78, HR 70 irregularly irregular. INR 2.4.\n"
            "A: Atrial fibrillation, unspecified (I48.91), stable on anticoagulation.\n"
            "P: Continue current regimen. INR monthly. Return in 6 months."
        ),
        "follow_ups": [("INR check", -90, True)],
    },
    {
        "mrn": "CEIS-1006", "provider": "d.reyes@example.org", "offset": -1, "type": "telehealth",
        "chief_complaint": "Seasonal allergies",
        "note": (
            "S: 41yo F with sneezing, itchy watery eyes, and clear rhinorrhea for 2 weeks, same time every spring "
            "and fall. No fever or facial pain.\n"
            "O: Video exam: allergic shiners, clear nasal discharge. No respiratory distress.\n"
            "A: Allergic rhinitis due to pollen (J30.1).\n"
            "P: Fluticasone nasal spray 2 sprays each nostril daily. Cetirizine 10 mg daily as needed."
        ),
        "follow_ups": [],
    },
]

ICD10_CODES = [
    ("E03.9", "Hypothyroidism, unspecified", "Endocrine"),
    ("E11.9", "Type 2 diabetes mellitus without complications", "Endocrine"),
    ("E11.42", "Type 2 diabetes mellitus with diabetic polyneuropathy", "Endocrine"),
    ("E11.65", "Type 2 diabetes mellitus with hyperglycemia", "Endocrine"),
    ("E66.9", "Obesity, unspecified", "Endocrine"),
    ("E78.5", "Hyperlipidemia, unspecified", "Endocrine"),
    ("F17.210", "Nicotine dependence, cigarettes, uncomplicated", "Mental and behavioral"),
    ("F32.1", "Major depressive disorder, single episode, moderate", "Mental and behavioral"),
    ("F41.1", "Generalized anxiety disorder", "Mental and behavioral"),
    ("G44.209", "Tension-type headache, unspecified, not intractable", "Nervous system"),
    ("G43.909", "Migraine, unspecified, not intractable, without status migrainosus", "Nervous system"),
    ("I10", "Essential (primary) hypertension", "Circulatory"),
    ("I20.8", "Other forms of angina pectoris", "Circulatory"),
    ("I25.10", "Atherosclerotic heart disease of native coronary artery without angina pectoris", "Circulatory"),
    ("I48.91", "Unspecified atrial fibrillation", "Circulatory"),
    ("I50.22", "Chronic systolic (congestive) heart failure", "Circulatory"),
    ("I50.9", "Heart failure, unspecified", "Circulatory"),
    ("J02.0", "Streptococcal pharyngitis", "Respiratory"),
    ("J02.9", "Acute pharyngitis, unspecified", "Respiratory"),
    ("J06.9", "Acute upper respiratory infection, unspecified", "Respiratory"),
    ("J18.9", "Pneumonia, unspecified organism", "Respiratory"),
    ("J30.1", "Allergic rhinitis due to pollen", "Respiratory"),
    ("J45.909", "Unspecified asthma, uncomplicated", "Respiratory"),
    ("K21.9", "Gastro-esophageal reflux disease without esophagitis", "Digestive"),
    ("M16.12", "Unilateral primary osteoarthritis, left hip", "Musculoskeletal"),
    ("M17.11", "Unilateral primary osteoarthritis, right knee", "Musculoskeletal"),
    ("M54.50", "Low back pain, unspecified", "Musculoskeletal"),
    ("N18.3", "Chronic kidney disease, stage 3 (moderate)", "Genitourinary"),
    ("N39.0", "Urinary tract infection, site not specified", "Genitourinary"),
    ("R05.9", "Cough, unspecified", "Symptoms and signs"),
    ("R06.02", "Shortness of breath", "Symptoms and signs"),
    ("R50.9", "Fever, unspecified", "Symptoms and signs"),
    ("R51.9", "Headache, unspecified", "Symptoms and signs"),
    ("R53.83", "Other fatigue", "Symptoms and signs"),
]

# (drug_a, drug_b, severity, description); the loader sorts each pair alphabetically.
DRUG_INTERACTIONS = [
    ("warfarin", "ibuprofen", "high", "NSAIDs increase bleeding risk with warfarin and can raise INR."),
    ("warfarin", "naproxen", "high", "NSAIDs increase bleeding risk with warfarin and can raise INR."),
    ("warfarin", "aspirin", "high", "Additive antiplatelet/anticoagulant effect; major bleeding risk."),
    ("warfarin", "clarithromycin", "high", "CYP3A4 inhibition raises warfarin levels; monitor INR closely."),
    ("sertraline", "tramadol", "high", "Risk of serotonin syndrome and lowered seizure threshold."),
    ("fluoxetine", "tramadol", "high", "Risk of serotonin syndrome and lowered seizure threshold."),
    ("sertraline", "ibuprofen", "moderate", "SSRIs plus NSAIDs increase GI bleeding risk."),
    ("simvastatin", "clarithromycin", "high", "Strong CYP3A4 inhibitor raises simvastatin levels; risk of rhabdomyolysis."),
    ("atorvastatin", "clarithromycin", "moderate", "CYP3A4 inhibition raises atorvastatin levels; myopathy risk."),
    ("lisinopril", "spironolactone", "moderate", "Combined potassium retention; risk of hyperkalemia."),
    ("lisinopril", "ibuprofen", "moderate", "NSAIDs blunt ACE inhibitor effect and raise risk of kidney injury."),
    ("metformin", "iodinated contrast", "moderate", "Hold metformin around contrast studies due to lactic acidosis risk."),
    ("levothyroxine", "calcium carbonate", "low", "Calcium reduces levothyroxine absorption; separate by 4 hours."),
    ("amlodipine", "simvastatin", "moderate", "Amlodipine raises simvastatin levels; limit simvastatin to 20 mg."),
]
