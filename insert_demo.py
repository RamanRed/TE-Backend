import json
import os
from src.database.prisma_client import get_prisma

def main():
    db = get_prisma()
    
    # Get a user
    user = db.user.find_first(include={"org": True})
    if not user:
        print("No users found!")
        return
        
    org_id = user.orgId
    user_id = user.id
    master_id = user.id # just use same for demo
    
    session = db.analysissession.create(
        data={
            "userId": user_id,
            "orgId": org_id,
            "masterUserId": master_id,
            "query": "Demo: Unexpected Conveyor Belt Stoppage",
            "domain": "Manufacturing",
            "title": "Demo: Conveyor Belt Incident",
            "isFinalized": True
        }
    )
    
    ishikawa_data = [
        {
            "id": "machine",
            "category": "Machine",
            "result": [
                {
                    "sub_category": "Motor",
                    "cause": "Overheated due to continuous heavy load",
                    "evidence": "Thermal sensor logged 115C",
                    "severity": "Critical",
                    "status": "confirmed",
                    "immediate_action": True
                }
            ]
        },
        {
            "id": "method",
            "category": "Method",
            "result": [
                {
                    "sub_category": "Maintenance",
                    "cause": "Preventative maintenance schedule was skipped",
                    "evidence": "Log shows no PM in 3 months",
                    "severity": "High",
                    "status": "confirmed",
                    "immediate_action": True
                }
            ]
        }
    ]
    
    five_whys_data = [
        {
            "problem_id": "Motor Overheating",
            "root_cause": "No automated alerts for skipped preventative maintenance routines.",
            "confidence": 0.95,
            "why_chain": [
                {
                    "level": 1,
                    "question": "Why did the motor overheat?",
                    "answer": "It accumulated too much debris and lacked lubrication."
                },
                {
                    "level": 2,
                    "question": "Why did it lack lubrication?",
                    "answer": "The PM schedule was skipped."
                },
                {
                    "level": 3,
                    "question": "Why was the PM schedule skipped?",
                    "answer": "No automated alerts to remind the team."
                }
            ]
        }
    ]
    
    ishikawa = db.savedishikawa.create(
        data={
            "sessionId": session.id,
            "userId": user_id,
            "masterUserId": master_id,
            "orgId": org_id,
            "problemQuery": "Demo: Unexpected Conveyor Belt Stoppage",
            "domain": "Manufacturing",
            "categoryCount": 2,
            "causeCount": 2,
            "mainCause": [
                "Motor overheated due to continuous heavy load",
                "Preventative maintenance schedule was skipped"
            ],
            "data": json.dumps(ishikawa_data),
            "isFinal": True
        }
    )
    
    db.savedfivewhys.create(
        data={
            "sessionId": session.id,
            "ishikawaId": ishikawa.id,
            "userId": user_id,
            "masterUserId": master_id,
            "orgId": org_id,
            "problemQuery": "Demo: Unexpected Conveyor Belt Stoppage",
            "domain": "Manufacturing",
            "chainCount": 1,
            "rootCauses": ["No automated alerts for skipped preventative maintenance routines."],
            "data": json.dumps(five_whys_data)
        }
    )
    
    print("Demo entry created successfully!")

if __name__ == '__main__':
    main()
