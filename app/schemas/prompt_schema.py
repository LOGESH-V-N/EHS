schema = """
{
	"document_type": "",
	"Overview": {
		"sender_information": {
			"name": "",
			"designation": "",
			"department": "",
			"contact_number": "",
			"email": ""
		},
		"letter_issued_date": {
			"date": "",
			"time": ""
		},
		"event_details": {
			"event_date": "",
			"event_time": ""
		},
		"hospital_details": {
			"hospital_name": "",
			"street_address": "",
			"city": "",
			"region": "",
			"country": "",
			"postcode": ""
		}
	},
	"patient_info": {
		"full_name": "",
		"nhs_number": "",
		"date_of_birth": "",
		"gender": "",
		"mobile_number": "",
		"landline_number": "",
		"email_address": "",
		"address": ""
	},
	"clinical_info": {
		"summary": {
			"short_summary": ""
		},
		"problems": [
			{
				"problem_name": "",
				"snomed_code": "",
				"severity": "",
				"date_identified": ""
			}
		],
		"treatment": [
			{
				"treatment_name": "",
				"snomed_code": "",
				"start_date": "",
				"end_date": "",
				"frequency": "",
				"dosage": ""
			}
		],
		"Medication_Plan": {
			"start_medication": [
				{
					"medication_name": "",
					"dosage": "",
					"frequency": "",
					"duration": "",
					"snomed_code": ""
				}
			],
			"change_medication": [
				{
					"medication_name": "",
					"dosage": "",
					"frequency": "",
					"duration": "",
					"snomed_code": ""
				}
			],
			"continue_medication": [
				{
					"medication_name": "",
					"dosage": "",
					"frequency": "",
					"duration": "",
					"snomed_code": ""
				}
			]
		},
		"investigations": [
			{
				"investigation_name": "",
				"snomed_code": "",
				"status": "",
				"performed_date": ""
			}
		],
		"diagnosis": [
			{
				"diagnosis_name": "",
				"snomed_code": "",
				"severity": "",
				"date_identified": ""
			}
		],
		"conclusion": [
			{
				"description": ""
			}
		]
	},
	"actions": {
		"follow_up": [
			{
				"follow_up_text": "",
				"follow_up_timeframe_or_date": ""
			}
		],
		"appointment": [
			{
				"appointment_text": "",
				"appointment_date_time": ""
			}
		],
		"actions": [
			{
				"action_text": "",
				"due_date_or_timeframe": ""
			}
		]
	}
}
"""