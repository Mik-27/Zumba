import json
from datetime import datetime
import mongo as mg

# with open('response.json', 'r') as file:
#     payload = json.load(file)

def process_webhook(payload):

    if payload["event"] == "meeting.participant_joined":
        
        user_id = payload["payload"]["object"]["participant"]["user_id"]
        user_name = payload["payload"]["object"]["participant"]["user_name"]
        join_time = payload["payload"]["object"]["participant"]["join_time"]
        join_time = datetime.strptime(join_time, "%Y-%m-%dT%H:%M:%SZ")
        meeting_id = payload["payload"]["object"]["id"]

        mg.add_presence_entry(meeting_id=meeting_id, user_id=user_id, user_name=user_name, join_time=join_time)

    elif payload["event"] == "meeting.participant_left":
        user_id = payload["payload"]["object"]["participant"]["user_id"]
        user_name = payload["payload"]["object"]["participant"]["user_name"]
        leave_time = payload["payload"]["object"]["participant"]["leave_time"]
        leave_time = datetime.strptime(leave_time, "%Y-%m-%dT%H:%M:%SZ")
        meeting_id = payload["payload"]["object"]["id"]

        mg.add_leave_time(meeting_id=meeting_id, user_id=user_id, leave_time=leave_time)

    elif payload["event"] == "meeting.participant_qos_summary":
        pass

    elif payload["event"] == "meeting.participant_data":
        #handle some useless responses
        user_id = payload["payload"]["object"]["participant"]["participant_id"]
        meeting_id = payload["payload"]["object"]["id"]
        if len(payload["payload"]["object"]["participant"]["data"]) > 0:
            mg.increment_participant_field(meeting_id=meeting_id, user_id=user_id, field_name="engagement_score", increment_value=1)
        else:
            pass

    elif payload["event"] == "meeting.started":
        meeting_id = payload["payload"]["object"]["id"]
        duration = payload["payload"]["object"]["duration"]
        start_time = payload["payload"]["object"]["start_time"]
        mg.insert_meeting_data(meeting_id=meeting_id, duration=duration, start_time=start_time)

    elif payload["event"] == "meeting.ended":
        meeting_id = payload["payload"]["object"]["id"]
        duration = meeting_id = payload["payload"]["object"]["duration"]
        start_time = meeting_id = payload["payload"]["object"]["start_time"]
        mg.add_final_score(meeting_id=meeting_id) 

    elif payload["event"] == "participant_qos_summary":
        pass
        
    else:
        print("Invalid event type")