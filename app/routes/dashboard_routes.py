from flask import Blueprint, request, jsonify
from app.models.ehs_document import Document
from app.models.ehs_count_master import Count
from app.models.document import DocTypeMaster
from app.models.ehs_patient import DocumentListSchema
from app.models.document import DocTypeMaster
from app.models.user import User
from app.models.ehs_doc_task import EhsDocumentTask
from app.models.ehs_doc_priority import Ehs_Doc_Priority
from app.utils.date_formatter import formated_datetime
from app.models.ehs_log import Log
from sqlalchemy import func
from app.extensions import db
from datetime import date

dashboard_bp= Blueprint("dashboard_bp", __name__)



@dashboard_bp.route("/overview", methods=["POST"])
def get_overview():
    try:
        overall_doc_count = Document.query.filter_by(delete_status=0).count()
        uploaded_doc_count = Document.query.filter_by(delete_status=0, doc_status=1).count()
        queued_doc_count = Document.query.filter_by(delete_status=0, doc_status=1).count()
        processing_count = Document.query.filter_by(delete_status=0, doc_status=2).count()
        processed_doc_count = Document.query.filter_by(delete_status=0, doc_status=3).count()
        assigned_to_doc_count = Document.query.filter_by(delete_status=0, doc_status=4).count()
        saved_doc_count = Document.query.filter_by(delete_status=0, doc_status=5).count()
        archived_doc_count = Document.query.filter_by(delete_status=0, doc_status=6).count()
        query_doc_count = Document.query.filter_by(delete_status=0, doc_status=7).count()
        in_process_doc_count = Document.query.filter(Document.delete_status == 0,Document.doc_status != 5).count()
 
        processed_percentage = (processed_doc_count / overall_doc_count) * 100
        saved_percentage = (saved_doc_count / overall_doc_count) * 100
 
        return jsonify({
            "status": 1,
            "message": "Documents fetched successfully",
            "data":{
                "overview_data":{
                    "all": overall_doc_count,
                    "uploaded": uploaded_doc_count,
                    "queued": queued_doc_count,
                    "processing": processing_count,
                    "processed": processed_doc_count,
                    "assigned": assigned_to_doc_count,
                    "saved": saved_doc_count,
                    "archived": archived_doc_count,
                    "query": query_doc_count
                },
                "processed_data":{
                    "label":"Document Completed",
                    "value":processed_percentage
                },
                "saved_data":{
                    "label":"Task Completed",
                    "value":saved_percentage
                },
                "doc_overview_data":{
                    "uploaded": overall_doc_count,
                    "in_progress": in_process_doc_count,
                    "saved": saved_doc_count
                },
                "pie_overview_data":{
                    "total_documents": overall_doc_count,
                    "uploaded": uploaded_doc_count,
                    "queued": queued_doc_count,
                    "processed": processed_doc_count,
                    "assigned": assigned_to_doc_count,
                    "saved": saved_doc_count,
                    "archived": archived_doc_count,
                    "query": query_doc_count
                }
            }
        }), 200
    except Exception as e:
        return jsonify({
            "status": 0,
            "message": str(e)
        }), 200
        
       
        
@dashboard_bp.route("/recent_documents", methods=["POST"])
def get_recent_documents():
    try:
        data=request.get_json()
        code=data.get("code")
 
        count_master=Count.query.filter_by(code=code).first()
        code_id=count_master.id
 
        if code_id == None:
            return jsonify({
                "status": 0,
                "message": "Invalid code"
            }), 200
 
       
 
        recent_documents = Document.query.filter_by(delete_status=0, doc_status=code_id).order_by(Document.created_at.desc()).limit(10).all()
        if not recent_documents:
            return jsonify({
                "status": 0,
                "message": "No recent documents found"
            }), 200
 
        documents_list = []
        print(recent_documents)
       
        for doc in recent_documents:
            patient = DocumentListSchema.query.filter_by(doc_id=doc.doc_id).first()
 
            patient_name = patient.patient_name if patient and patient.patient_name else "N/A"
            phone_no = patient.phone_no if patient and patient.phone_no else "N/A"
            user=User.query.filter_by(uid=doc.assign_to).first()
            user_name=user.name if user and user.name else "N/A"
            error_message=doc.error_message if doc and doc.error_message else "N/A"
            doc_type = DocTypeMaster.query.filter_by(
                doc_type_code=doc.doc_type_code
            ).first()
 
            doc_type_name = doc_type.doc_type_name if doc_type else "N/A"
            doc_type_name = doc_type.doc_type_name if doc_type else "N/A"
            query=Log.query.filter_by(doc_id=doc.doc_id, doc_status=2).first()
            query_date=query.datatime if query else None
            processed=Log.query.filter_by(doc_id=doc.doc_id, doc_status=3).first()
            processed_date=processed.datatime if processed else None
            saved=Log.query.filter_by(doc_id=doc.doc_id, doc_status=5).first()
            saved_date=saved.datatime if saved else None
            print(saved_date)
            assigned=Log.query.filter_by(doc_id=doc.doc_id, doc_status=4).first()
            assigned_date=assigned.datatime if assigned else None
            query=Log.query.filter_by(doc_id=doc.doc_id, doc_status=7).first()
            query_date=query.datatime if query else None
            archived=Log.query.filter_by(doc_id=doc.doc_id, doc_status=6).first()
            archived_date=archived.datatime if archived else None
 
 
            print(doc_type_name)
           
            #print("how are you")
            doc_data=({
                "id": doc.doc_id,
                "document_name": doc.doc_filename,
                "doc_status": doc.doc_status,    
                "patient_name": patient_name,
                "patient_no": phone_no,
                "delete_status": doc.delete_status,
                "document_type": doc_type_name
            })
            #print("hello")
 
            if code == "uploaded":
                doc_data["created_at"] = formated_datetime(doc.created_at)
            if code == "queued":
                doc_data["queued_date"] = formated_datetime(query_date)
            if code == "processed":
                doc_data["processed_date"] = formated_datetime(processed_date)
            if code == "saved":
                doc_data["assigned_to"] = user_name
                doc_data["assigned_date"] = formated_datetime(doc.assigned_date)
                doc_data["saved_date"] = formated_datetime(saved_date)
            if code== "assigned":
                doc_data["assigned_to"] = user_name
                doc_data["assigned_date"] = formated_datetime(doc.assigned_date)
                doc_data["assigned_date"] = formated_datetime(assigned_date)
            if code == "querys":
                doc_data["error_message"] = error_message
                doc_data["query_date"] = formated_datetime(query_date)
            if code == "archived":
                doc_data["archived_date"] = formated_datetime(archived_date)
            #print("how old are you")
            documents_list.append(doc_data)
            #print("i am fine")
        #print(documents_list)
           
 
        return jsonify({
            "status": 1,
            "message": "Recent documents fetched successfully",
            "data": documents_list
        }), 200
    except Exception as e:
        return jsonify({
            "status": 0,
            "message": str(e)
        }), 200
 
 








@dashboard_bp.route("/monthly_count", methods=["POST"])
def get_monthly_count():
    try:
        monthly_data = db.session.query(
            func.month(Document.created_at).label("month_no"),
            func.monthname(Document.created_at).label("month_name"),
            func.count(Document.doc_id).label("count")
        ).filter(
            Document.delete_status == 0,
            Document.doc_status == 3
        ).group_by(
            func.month(Document.created_at),
            func.monthname(Document.created_at)
        ).order_by(
            func.month(Document.created_at)
        ).limit(12).all()

        processed_date = []

        for month_no, month_name, count in monthly_data:
            processed_date.append({
                "month": month_name,
                "count": count
            })


        monthly_document_counts = db.session.query(
            func.DATE_FORMAT(Document.created_at, "%b").label("month"),   # <-- changed
            func.count(Document.doc_id).label("count")
        ).filter(
            Document.delete_status == 0
        ).group_by(
            func.DATE_FORMAT(Document.created_at, "%Y-%b")   # <-- changed
        ).order_by(
            func.DATE_FORMAT(Document.created_at, "%Y-%m")   # sorting by numeric month
        ).limit(12).all()

        month_data=[]
        for month, count in monthly_document_counts:
            month_data.append({
                "month": month,
                "count": count
            })


        return jsonify({
            "status": 1,
            "message": "Monthly document count and processed count fetched successfully",
            "data": {
                "month_data": month_data,
                "processed_date": processed_date
            }
        }), 200
    
    except Exception as e:
        return jsonify({
            "status": 0,
            "message": str(e)
        }), 200

@dashboard_bp.route("/assigned_date_counts", methods=["POST"])
def get_assigned_date_counts():
    try:
        # Calculate date differences for assigned documents
        # DATEDIFF(date1, date2) returns the number of days between date1 and date2.
        # We want to know how many days ago a document was assigned, so DATEDIFF(CURRENT_DATE(), Document.assigned_date).

        # 1 to 3 days ago
        count_1_3_days = Document.query.filter(
            Document.delete_status == 0,
            Document.assigned_date.isnot(None), # Ensure assigned_date is not null
            func.DATEDIFF(func.CURRENT_DATE(), Document.assigned_date).between(1, 3)
        ).count()

        # 4 to 7 days ago
        count_4_10_days = Document.query.filter(
            Document.delete_status == 0,
            Document.assigned_date.isnot(None),
            func.DATEDIFF(func.CURRENT_DATE(), Document.assigned_date).between(4, 10)
        ).count()

        # 11 to 20 days ago
        count_11_20_days = Document.query.filter(
            Document.delete_status == 0,
            Document.assigned_date.isnot(None),
            func.DATEDIFF(func.CURRENT_DATE(), Document.assigned_date).between(11, 20)
        ).count()

        count_21_30_days = Document.query.filter(
            Document.delete_status == 0,
            Document.assigned_date.isnot(None),
            func.DATEDIFF(func.CURRENT_DATE(), Document.assigned_date).between(21, 30)
        ).count()

        # 11 and above days ago (i.e., 12 days or more)
        count_31_plus_days = Document.query.filter(
            Document.delete_status == 0,
            Document.assigned_date.isnot(None),
            func.DATEDIFF(func.CURRENT_DATE(), Document.assigned_date) >= 31
        ).count()

        return jsonify({
            "status": 1,
            "message": "Assigned date counts fetched successfully",
             "data": {
                "days_ago_from_0_to_3": count_1_3_days,
                "days_ago_from_4_to_10": count_4_10_days,
                "days_ago_from_11_to_20": count_11_20_days,
                "days_ago_from_21_to_30": count_21_30_days,
                "days_ago_from_31_plus": count_31_plus_days
            },
            "values":[count_1_3_days,count_4_10_days,count_11_20_days,count_21_30_days,count_31_plus_days]
        }),200
    except Exception as e:
        return jsonify({
            "status": 0,
            "message": str(e)
        }),200


@dashboard_bp.route("/document_type_count", methods=["POST"])
def get_document_type_count():
    try:
        doc_type_master = DocTypeMaster.query.all() 
        document_type_counts = []
        uploaded_total=0
        queued_total=0
        processed_total=0
        assigned_total=0
        saved_total=0
        archived_total=0
        query_total=0
        for doc_type in doc_type_master:
            document_name=doc_type.doc_type_name
            document_code = doc_type.doc_type_code
            all_ehs_doc=Document.query.filter_by(doc_type_code=document_code)
            all_ehs_doc_uploaded_count=all_ehs_doc.filter_by(delete_status=0).count()
            all_ehs_doc_qeued_count=all_ehs_doc.filter_by(doc_status=1).count()
            all_ehs_doc_processed_count=all_ehs_doc.filter_by(doc_status=3).count()
            all_ehs_doc_assigned_count=all_ehs_doc.filter_by(doc_status=4).count()
            all_ehs_doc_saved_count=all_ehs_doc.filter_by(doc_status=5).count()
            all_ehs_doc_archived_count=all_ehs_doc.filter_by(doc_status=6).count()
            all_ehs_doc_query_count=all_ehs_doc.filter_by(doc_status=7).count()
            total=all_ehs_doc_uploaded_count+all_ehs_doc_qeued_count+all_ehs_doc_processed_count+all_ehs_doc_assigned_count+all_ehs_doc_saved_count+all_ehs_doc_archived_count+all_ehs_doc_query_count
            uploaded_total+=all_ehs_doc_uploaded_count
            queued_total+=all_ehs_doc_qeued_count
            processed_total+=all_ehs_doc_processed_count
            assigned_total+=all_ehs_doc_assigned_count
            saved_total+=all_ehs_doc_saved_count
            archived_total+=all_ehs_doc_archived_count
            query_total+=all_ehs_doc_query_count
            document_type_counts.append({
                "document_name": document_name,
                "document_code": document_code,
                "values":{"uploaded": all_ehs_doc_uploaded_count,
                "queued": all_ehs_doc_qeued_count,
                "processed": all_ehs_doc_processed_count,
                "assigned": all_ehs_doc_assigned_count,
                "saved": all_ehs_doc_saved_count,
                "archived": all_ehs_doc_archived_count,
                "query": all_ehs_doc_query_count,
                "total":total}
            })  

        return jsonify({
            "status": 1,
            "message": "Document type count fetched successfully",
            "data": {
                "document_type_counts":document_type_counts,
                "uploaded_total":uploaded_total,
                "queued_total":queued_total,
                "processed_total":processed_total,
                "assigned_total":assigned_total,
                "saved_total":saved_total,
                "archived_total":archived_total,
                "query_total":query_total
                }
        }), 200
                
                


    except Exception as e:
        return jsonify({
            "status": 0,
            "message": str(e)
        }),200

@dashboard_bp.route("/document_list", methods=["POST"])
def get_document_list():
    try:
        doc_list = Document.query.filter_by(delete_status=0).order_by(Document.created_at.desc()).limit(10).all()
        document_list = []

        for doc in doc_list:
            document_name = doc.doc_filename

            # ---- Patient info (SAFE) ----
            patient = DocumentListSchema.query.filter_by(doc_id=doc.doc_id).first()

            patient_name = patient.patient_name if patient and patient.patient_name else "N/A"
            phone_no = patient.phone_no if patient and patient.phone_no else "N/A"

            # ---- Letter type (SAFE) ----
            doc_type = DocTypeMaster.query.filter_by(doc_type_code=doc.doc_type_code).first()
            letter_type = doc_type.doc_type_name if doc_type else "N/A"

            # ---- Assigned user (SAFE) ----
            user = User.query.filter_by(uid=doc.assign_to).first()
            assigned_name = user.name if user else "N/A"

            # ---- Assigned date ----
            assigned_date = formated_datetime(doc.assigned_date) if doc.assigned_date else "N/A"

            # ---- Pending days (CORRECT) ----
            if doc.assigned_date:
                pending_days = (
                    db.session.query(
                        func.DATEDIFF(func.CURRENT_DATE(), doc.assigned_date)
                    ).scalar()
                )
                pending_days = f"{pending_days} days"
            else:
                pending_days = "N/A"
            document_list.append({
                "document_name": document_name,
                "patient_name": patient_name,
                "phone_no": phone_no,
                "letter_type": letter_type,
                "assigned_name": assigned_name,
                "assigned_date": assigned_date,
                "pending_days": pending_days
            })

            

        return jsonify({
            "status": 1,
            "message": "Document list fetched successfully",
            "data": document_list
        }), 200
    except Exception as e:
        return jsonify({
            "status": 0,
            "message": str(e)
        }), 200

@dashboard_bp.route("/incomplete_task", methods=["POST"])
def get_incomplete_task():
    try:
        incomplete_task = EhsDocumentTask.query.filter_by(task_status=1).all()
        incomplete_task_list = []
        for task in incomplete_task:
            incomplete_task_list.append({
                "task_name": task.task_name,
                "assignee":User.query.filter_by(uid=task.assign_to).first().name,
                "assigned_date":formated_datetime(task.created_at),
                "due_date":formated_datetime(task.due_date),
                "priority":Ehs_Doc_Priority.query.filter_by(id=task.priority_id).first().name,
                "priority_color_code":Ehs_Doc_Priority.query.filter_by(id=task.priority_id).first().color_code,
                "pending_days":(
                    db.session.query(
                        func.DATEDIFF(func.CURRENT_DATE(), task.due_date)
                    ).scalar()
                )+"days"
            })
        return jsonify({
            "status": 1,
            "message": "Incomplete task fetched successfully",
            "data": incomplete_task_list
        }), 200
    except Exception as e:
        return jsonify({
            "status": 0,
            "message": str(e)
        }), 200

@dashboard_bp.route("/assign_overview", methods=["POST"])
def get_assign_overview():
    try:
        data=request.get_json()
        id=data["id"]
        if not id:
            return jsonify({
                "status": 0,
            "message": "Invalid id"
        }), 200
        overall=Document.query.filter_by(delete_status=0).count()
        overall_assigned=Document.query.filter_by(delete_status=0, assign_to=id).count()
        assigned=Document.query.filter_by(delete_status=0, assign_to=id).all()
        
        assigned_count=0
        high_priority_count=0
        medium_priority_count=0
        low_priority_count=0
        for completed_count in assigned:
            doc_id=completed_count.doc_id
            tasks=EhsDocumentTask.query.filter_by(doc_id=doc_id).all()
            for task in tasks:      
                if task.task_status==2:
                    assigned_count+=1  
                if task.priority_id==1:
                    low_priority_count+=1
                if task.priority_id==2:
                    medium_priority_count+=1
                if task.priority_id==3:
                    high_priority_count+=1
        completed_percentage=(assigned_count/overall_assigned)*100

        return jsonify({
            "status": 1,
            "message": "Assign overview fetched successfully",
            "data": {
                "overall":{
                "overall":overall,
                "overall_assigned":overall_assigned,
                "completed_count":assigned_count,
                "high_priority_count":high_priority_count,
                "medium_priority_count":medium_priority_count,
                "low_priority_count":low_priority_count
                },
                "completed_percentage":completed_percentage,
                "donet_task":{
                    "assigned":overall_assigned,
                    "completed":assigned_count,
                    "incompleted":overall_assigned-assigned_count
                },
                "priority":{
                    "high":high_priority_count,
                    "medium":medium_priority_count,
                    "low":low_priority_count
                }
                }
        }), 200
    except Exception as e:
        return jsonify({
            "status": 0,
            "message": str(e)
        }), 200
    
            
            
from sqlalchemy import func

@dashboard_bp.route("/assign_month_wise", methods=["POST"])
def assign_month_wise():
    try:
        data = request.get_json() or {}
        user_id = data.get("id")

        if not user_id:
            return jsonify({
                "status": 0,
                "message": "Invalid id"
            }), 400

        results = db.session.query(
            func.MONTH(Document.created_at).label("month_no"),
            func.MONTHNAME(Document.created_at).label("month"),
            func.count(Document.doc_id).label("count")
        ).filter(
            Document.delete_status == 0,
            Document.assign_to == user_id
        ).group_by(
            func.MONTH(Document.created_at),
            func.MONTHNAME(Document.created_at)
        ).order_by(
            func.MONTH(Document.created_at)
        ).all()

        data = []
        for row in results:
            data.append({
                "month": row.month,
                "count": row.count
            })

        return jsonify({
            "status": 1,
            "message": "Assign month wise fetched successfully",
            "data": data
        }), 200

    except Exception as e:
        return jsonify({
            "status": 0,
            "message": str(e)
        }), 500

@dashboard_bp.route("/assign_table", methods=["POST"])
def assign_table():
    try:
        data=request.get_json()
        id=data["id"]
        if not id:
            return jsonify({
                "status": 0,
            "message": "Invalid id"
        }), 200
        doc_ids=Document.query.filter_by(assign_to=id).all()
        doc_ids_list=[]
        for doc_id in doc_ids:
            doc_id=doc_id.doc_id
            tasks=EhsDocumentTask.query.filter_by(doc_id=doc_id).all()
            for task in tasks:
                task_id=task.id
                task_name=task.task_name
                assign_to=task.assign_to
                assign_label=User.query.filter_by(uid=assign_to).first().name
                sub_title=task.sub_title
                note=task.note
                due_date=formated_datetime(task.due_date)
                priority_id=task.priority_id
                priority_label=Ehs_Doc_Priority.query.filter_by(id=priority_id).first().name
                priority_color_code=Ehs_Doc_Priority.query.filter_by(id=priority_id).first().color_code
                
                
                doc_ids_list.append({
                    "task_id":task_id,
                    "task_name":task_name,
                    "assign_to":assign_to,
                    "assign_label":assign_label,
                    "sub_title":sub_title,
                    "note":note,
                    "due_date":due_date,
                    "priority_id":priority_id,
                    "priority_label":priority_label,
                    "priority_color_code":priority_color_code
                })
                
        return jsonify({
            "status": 1,
            "message": "Assign table fetched successfully",
            "data": doc_ids_list
        }), 200
    except Exception as e:
        return jsonify({
            "status": 0,
            "message": str(e)
        }), 500
