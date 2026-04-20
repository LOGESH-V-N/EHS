from app.extensions import ma
from marshmallow import fields

class DocumentListSchema(ma.Schema):
    document_id = fields.Int()
    document_name = fields.Str()
    patient_info = fields.Str()
    letter_type = fields.Str()
    document_status = fields.Str()
    created_date = fields.Str()

# Single + multiple schema objects (important)
document_schema = DocumentListSchema()
documents_schema = DocumentListSchema(many=True)
