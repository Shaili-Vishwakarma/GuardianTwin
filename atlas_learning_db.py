"""
Atlas Database Integration for Rescue Learning
Stores mission data and enables iterative improvement.
"""

import os
from pymongo import MongoClient, DESCENDING
from typing import List, Dict, Optional
from datetime import datetime
from building_navigator import Position3D
from nemo_rescue_agents import RescueMission, AgentState
from dotenv import load_dotenv
import json


load_dotenv()


class AtlasLearningDatabase:
    """
    MongoDB Atlas database for storing rescue mission attempts.
    Enables agents to learn from past failures and successes.
    """

    def __init__(self):
        uri = os.getenv('MONGODB_URI')
        db_name = os.getenv('MONGODB_DATABASE', 'building_analysis')

        self.client = MongoClient(uri)
        self.db = self.client[db_name]

        # Collections
        self.missions_collection = self.db['rescue_missions']
        self.trajectories_collection = self.db['rescue_trajectories']
        self.learning_collection = self.db['rescue_learning']

        # Create indexes
        self._create_indexes()

        print("Atlas Learning Database initialized")

    def _create_indexes(self):
        """Create database indexes for efficient queries"""
        # Mission indexes
        self.missions_collection.create_index([("timestamp", DESCENDING)])
        self.missions_collection.create_index([("scenario", 1), ("success", 1)])
        self.missions_collection.create_index([("mission_id", 1)], unique=True)

        # Trajectory indexes
        self.trajectories_collection.create_index([("mission_id", 1)])
        self.trajectories_collection.create_index([("agent_id", 1)])
        self.trajectories_collection.create_index([("success", 1)])

        # Learning indexes
        self.learning_collection.create_index([("scenario", 1)])

    def store_mission(self, mission: RescueMission) -> str:
        """
        Store a complete rescue mission with all agent data.
        Returns the inserted document ID.
        """
        # Convert mission to database document
        doc = {
            "mission_id": mission.mission_id,
            "scenario": mission.scenario,
            "timestamp": datetime.utcnow(),
            "start_time": mission.start_time,
            "end_time": mission.end_time,
            "total_time": mission.total_time,
            "success": mission.success,
            "reason_failed": mission.reason_failed,
            "num_agents": len(mission.agents),
            "agents_alive": sum(1 for a in mission.agents if a.is_alive),
            "agents_rescued": sum(1 for a in mission.agents if a.has_child),
        }

        # Insert mission
        result = self.missions_collection.insert_one(doc)

        # Store individual agent trajectories
        self._store_trajectories(mission)

        # Update learning data
        self._update_learning_data(mission)

        print(f"Mission {mission.mission_id} stored in Atlas DB")
        return str(result.inserted_id)

    def _store_trajectories(self, mission: RescueMission):
        """Store individual agent trajectories"""
        trajectory_docs = []

        for agent_state in mission.agents:
            # Convert path to serializable format
            path_data = [
                {
                    'x': pos.x,
                    'y': pos.y,
                    'z': pos.z,
                    'floor': pos.floor
                }
                for pos in agent_state.path_taken
            ]

            doc = {
                "mission_id": mission.mission_id,
                "agent_id": agent_state.agent_id,
                "scenario": mission.scenario,
                "timestamp": datetime.utcnow(),
                "success": agent_state.has_child and agent_state.is_alive,
                "is_alive": agent_state.is_alive,
                "has_child": agent_state.has_child,
                "final_health": agent_state.health,
                "cumulative_danger": agent_state.cumulative_danger,
                "path": path_data,
                "path_length": len(path_data),
                "decisions": agent_state.decisions_made,
                "death_position": path_data[-1] if path_data and not agent_state.is_alive else None,
            }

            trajectory_docs.append(doc)

        if trajectory_docs:
            self.trajectories_collection.insert_many(trajectory_docs)

    def _update_learning_data(self, mission: RescueMission):
        """Update aggregated learning data"""
        # Get existing learning doc for this scenario
        learning_doc = self.learning_collection.find_one({"scenario": mission.scenario})

        if not learning_doc:
            learning_doc = {
                "scenario": mission.scenario,
                "total_attempts": 0,
                "successful_attempts": 0,
                "failed_attempts": 0,
                "avg_time_success": 0.0,
                "dangerous_positions": [],
                "successful_paths": [],
                "failure_reasons": {},
                "best_strategies": [],
            }

        # Update statistics
        learning_doc["total_attempts"] += 1

        if mission.success:
            learning_doc["successful_attempts"] += 1

            # Update average success time
            n = learning_doc["successful_attempts"]
            old_avg = learning_doc["avg_time_success"]
            learning_doc["avg_time_success"] = (old_avg * (n - 1) + mission.total_time) / n

            # Store successful paths
            for agent_state in mission.agents:
                if agent_state.has_child and agent_state.is_alive:
                    path_data = [
                        {'x': pos.x, 'y': pos.y, 'z': pos.z, 'floor': pos.floor}
                        for pos in agent_state.path_taken
                    ]
                    learning_doc["successful_paths"].append({
                        "path": path_data,
                        "time": mission.total_time,
                        "danger": agent_state.cumulative_danger
                    })

                    # Keep only best 10 paths
                    if len(learning_doc["successful_paths"]) > 10:
                        learning_doc["successful_paths"].sort(key=lambda x: x["time"])
                        learning_doc["successful_paths"] = learning_doc["successful_paths"][:10]

        else:
            learning_doc["failed_attempts"] += 1

            # Record failure reason
            reason = mission.reason_failed or "unknown"
            learning_doc["failure_reasons"][reason] = learning_doc["failure_reasons"].get(reason, 0) + 1

            # Record dangerous positions where agents died
            for agent_state in mission.agents:
                if not agent_state.is_alive and agent_state.path_taken:
                    death_pos = agent_state.path_taken[-1]
                    learning_doc["dangerous_positions"].append({
                        'x': death_pos.x,
                        'y': death_pos.y,
                        'z': death_pos.z,
                        'floor': death_pos.floor,
                        'danger': agent_state.cumulative_danger
                    })

                    # Keep only most recent 50 dangerous positions
                    if len(learning_doc["dangerous_positions"]) > 50:
                        learning_doc["dangerous_positions"] = learning_doc["dangerous_positions"][-50:]

        # Update or insert
        self.learning_collection.update_one(
            {"scenario": mission.scenario},
            {"$set": learning_doc},
            upsert=True
        )

    def get_learning_data(self, scenario: str) -> Dict:
        """
        Get aggregated learning data for a scenario.
        Used to improve future agent performance.
        """
        learning_doc = self.learning_collection.find_one({"scenario": scenario})

        if not learning_doc:
            return {
                "scenario": scenario,
                "total_attempts": 0,
                "missions": []
            }

        # Get recent missions
        recent_missions = list(self.missions_collection.find(
            {"scenario": scenario}
        ).sort("timestamp", DESCENDING).limit(20))

        # Convert to serializable format
        missions = []
        for mission in recent_missions:
            missions.append({
                "mission_id": mission.get("mission_id"),
                "success": mission.get("success", False),
                "total_time": mission.get("total_time", 0.0),
                "reason_failed": mission.get("reason_failed")
            })

        # Get successful trajectories for learning
        successful_trajectories = list(self.trajectories_collection.find(
            {"scenario": scenario, "success": True}
        ).sort("cumulative_danger", 1).limit(5))

        return {
            "scenario": scenario,
            "total_attempts": learning_doc.get("total_attempts", 0),
            "successful_attempts": learning_doc.get("successful_attempts", 0),
            "failed_attempts": learning_doc.get("failed_attempts", 0),
            "avg_time_success": learning_doc.get("avg_time_success", 0.0),
            "dangerous_positions": learning_doc.get("dangerous_positions", []),
            "successful_paths": learning_doc.get("successful_paths", []),
            "failure_reasons": learning_doc.get("failure_reasons", {}),
            "missions": missions,
            "best_trajectories": [
                {
                    "agent_id": t.get("agent_id"),
                    "path": t.get("path", []),
                    "danger": t.get("cumulative_danger", 0.0)
                }
                for t in successful_trajectories
            ]
        }

    def get_mission_statistics(self, scenario: Optional[str] = None) -> Dict:
        """Get overall statistics"""
        query = {}
        if scenario:
            query["scenario"] = scenario

        total = self.missions_collection.count_documents(query)
        successful = self.missions_collection.count_documents({**query, "success": True})
        failed = self.missions_collection.count_documents({**query, "success": False})

        success_rate = (successful / total * 100) if total > 0 else 0.0

        # Average times
        pipeline = [
            {"$match": {**query, "success": True}},
            {"$group": {
                "_id": None,
                "avg_time": {"$avg": "$total_time"},
                "min_time": {"$min": "$total_time"},
                "max_time": {"$max": "$total_time"}
            }}
        ]

        time_stats = list(self.missions_collection.aggregate(pipeline))

        return {
            "scenario": scenario or "all",
            "total_missions": total,
            "successful_missions": successful,
            "failed_missions": failed,
            "success_rate": round(success_rate, 2),
            "avg_time": round(time_stats[0]["avg_time"], 2) if time_stats else 0.0,
            "min_time": round(time_stats[0]["min_time"], 2) if time_stats else 0.0,
            "max_time": round(time_stats[0]["max_time"], 2) if time_stats else 0.0,
        }

    def store_guardian_cycle(self, cycle_data: dict) -> str:
        """
        Store one GuardianTwin agent cycle for audit and analysis.
        Does not affect existing rescue simulation collections.
        """
        guardian_collection = self.db['guardian_cycles']
        result = guardian_collection.insert_one({
            **cycle_data,
            'stored_at': datetime.utcnow(),
        })
        return str(result.inserted_id)

    def clear_scenario_data(self, scenario: str):
        """Clear all data for a scenario (for testing)"""
        self.missions_collection.delete_many({"scenario": scenario})
        self.trajectories_collection.delete_many({"scenario": scenario})
        self.learning_collection.delete_many({"scenario": scenario})
        print(f"Cleared all data for scenario: {scenario}")


if __name__ == "__main__":
    # Test the Atlas database
    print("Testing Atlas Learning Database")
    print("=" * 60)

    db = AtlasLearningDatabase()

    # Get statistics
    stats = db.get_mission_statistics()
    print("\nOverall Statistics:")
    print(json.dumps(stats, indent=2))

    # Get learning data for fire scenario
    learning = db.get_learning_data("fire")
    print(f"\nFire Scenario Learning Data:")
    print(f"Total Attempts: {learning['total_attempts']}")
    print(f"Successful: {learning['successful_attempts']}")
    print(f"Failed: {learning['failed_attempts']}")
