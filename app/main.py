from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from uuid import uuid4
import nflreadpy as nfl
from datetime import datetime

from app.db import engine, SessionLocal

app = FastAPI()


@app.get("/")
def read_root():
    return {"message": "Confidence Pool API is running"}


@app.get("/db-test")
def db_test():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        return {"db_response": [row[0] for row in result]}


@app.post("/users")
def create_user(email: str, display_name: str):
    db = SessionLocal()
    try:
        user_id = str(uuid4())

        db.execute(
            text("""
                insert into users (id, email, display_name)
                values (:id, :email, :display_name)
            """),
            {
                "id": user_id,
                "email": email,
                "display_name": display_name
            }
        )
        db.commit()

        return {
            "id": user_id,
            "email": email,
            "display_name": display_name
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()


@app.get("/users")
def get_users():
    db = SessionLocal()
    try:
        result = db.execute(
            text("""
                select id, email, display_name, created_at
                from users
                order by created_at desc
            """)
        )

        users = []
        for row in result:
            users.append({
                "id": str(row.id),
                "email": row.email,
                "display_name": row.display_name,
                "created_at": row.created_at.isoformat() if row.created_at else None
            })

        return users
    finally:
        db.close()
        
@app.post("/pools")
def create_pool(name: str, commissioner_user_id: str, season_year: int):
    db = SessionLocal()
    try:
        pool_id = str(uuid4())

        db.execute(
            text("""
                insert into pools (id, name, commissioner_user_id, season_year)
                values (:id, :name, :commissioner_user_id, :season_year)
            """),
            {
                "id": pool_id,
                "name": name,
                "commissioner_user_id": commissioner_user_id,
                "season_year": season_year
            }
        )

        # commissioner is also a member
        db.execute(
            text("""
                insert into pool_members (pool_id, user_id, role)
                values (:pool_id, :user_id, 'commissioner')
            """),
            {
                "pool_id": pool_id,
                "user_id": commissioner_user_id
            }
        )

        db.commit()

        return {"pool_id": pool_id}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()
        
@app.post("/pools/{pool_id}/join")
def join_pool(pool_id: str, user_id: str):
    db = SessionLocal()
    try:
        db.execute(
            text("""
                insert into pool_members (pool_id, user_id)
                values (:pool_id, :user_id)
            """),
            {
                "pool_id": pool_id,
                "user_id": user_id
            }
        )
        db.commit()

        return {"message": "joined"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()
        
@app.get("/pools/{pool_id}")
def get_pool(pool_id: str):
    db = SessionLocal()
    try:
        pool = db.execute(
            text("""
                select id, name, commissioner_user_id, season_year
                from pools
                where id = :pool_id
            """),
            {"pool_id": pool_id}
        ).fetchone()

        if not pool:
            raise HTTPException(status_code=404, detail="Pool not found")

        members = db.execute(
            text("""
                select u.id, u.display_name, pm.role
                from pool_members pm
                join users u on u.id = pm.user_id
                where pm.pool_id = :pool_id
            """),
            {"pool_id": pool_id}
        )

        return {
            "id": pool.id,
            "name": pool.name,
            "season_year": pool.season_year,
            "members": [
                {
                    "id": str(row.id),
                    "display_name": row.display_name,
                    "role": row.role
                }
                for row in members
            ]
        }

    finally:
        db.close()
        
@app.post("/weeks")
def create_week(
    season_year: int,
    week_number: int,
    week_type: str = "regular",
    start_date: str | None = None,
    end_date: str | None = None
):
    db = SessionLocal()
    try:
        result = db.execute(
            text("""
                insert into weeks (season_year, week_number, week_type, start_date, end_date)
                values (:season_year, :week_number, :week_type, :start_date, :end_date)
                returning id, season_year, week_number, week_type, start_date, end_date
            """),
            {
                "season_year": season_year,
                "week_number": week_number,
                "week_type": week_type,
                "start_date": start_date,
                "end_date": end_date
            }
        )
        row = result.fetchone()
        db.commit()

        return {
            "id": str(row.id),
            "season_year": row.season_year,
            "week_number": row.week_number,
            "week_type": row.week_type,
            "start_date": row.start_date.isoformat() if row.start_date else None,
            "end_date": row.end_date.isoformat() if row.end_date else None,
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()
        
@app.post("/games")
def create_game(
    week_id: str,
    kickoff_at: str,
    away_team: str,
    home_team: str
):
    db = SessionLocal()
    try:
        result = db.execute(
            text("""
                insert into games (week_id, kickoff_at, away_team, home_team)
                values (:week_id, :kickoff_at, :away_team, :home_team)
                returning id, week_id, kickoff_at, away_team, home_team, status
            """),
            {
                "week_id": week_id,
                "kickoff_at": kickoff_at,
                "away_team": away_team,
                "home_team": home_team
            }
        )
        row = result.fetchone()
        db.commit()

        return {
            "id": str(row.id),
            "week_id": str(row.week_id),
            "kickoff_at": row.kickoff_at.isoformat(),
            "away_team": row.away_team,
            "home_team": row.home_team,
            "status": row.status
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()
        
@app.get("/weeks/{week_id}/games")
def get_games_for_week(week_id: str):
    db = SessionLocal()
    try:
        week = db.execute(
            text("""
                select id, season_year, week_number, week_type, start_date, end_date
                from weeks
                where id = :week_id
            """),
            {"week_id": week_id}
        ).fetchone()

        if not week:
            raise HTTPException(status_code=404, detail="Week not found")

        results = db.execute(
            text("""
                select id, kickoff_at, away_team, home_team, status,
                       away_score, home_score, winning_team, is_tie
                from games
                where week_id = :week_id
                order by kickoff_at asc, away_team asc, home_team asc
            """),
            {"week_id": week_id}
        )

        games = []
        for row in results:
            games.append({
                "id": str(row.id),
                "kickoff_at": row.kickoff_at.isoformat(),
                "away_team": row.away_team,
                "home_team": row.home_team,
                "status": row.status,
                "away_score": row.away_score,
                "home_score": row.home_score,
                "winning_team": row.winning_team,
                "is_tie": row.is_tie
            })

        return {
            "week": {
                "id": str(week.id),
                "season_year": week.season_year,
                "week_number": week.week_number,
                "week_type": week.week_type,
                "start_date": week.start_date.isoformat() if week.start_date else None,
                "end_date": week.end_date.isoformat() if week.end_date else None,
            },
            "games": games
        }
    finally:
        db.close()
        
@app.post("/admin/import-schedule/{season_year}")
def import_schedule(season_year: int):
    db = SessionLocal()
    try:
        df = nfl.load_schedules([season_year])

        # Only regular season
        df = df.filter(df["game_type"] == "REG")

        week_map = {}

        # --- Create or fetch weeks ---
        for week_number in sorted(df["week"].unique().to_list()):
            result = db.execute(
                text("""
                    insert into weeks (season_year, week_number, week_type)
                    values (:season_year, :week_number, 'regular')
                    on conflict (season_year, week_number, week_type) do nothing
                    returning id
                """),
                {
                    "season_year": season_year,
                    "week_number": int(week_number),
                }
            ).fetchone()

            if result:
                week_id = result.id
            else:
                existing = db.execute(
                    text("""
                        select id
                        from weeks
                        where season_year = :season_year
                          and week_number = :week_number
                          and week_type = 'regular'
                    """),
                    {
                        "season_year": season_year,
                        "week_number": int(week_number),
                    }
                ).fetchone()

                week_id = existing.id

            week_map[int(week_number)] = week_id

        inserted_games = 0

        # --- Insert games ---
        for row in df.iter_rows(named=True):
            week_number = int(row["week"])
            week_id = week_map[week_number]

            gameday = row["gameday"]
            gametime = row["gametime"]

            if gameday is None or gametime is None:
                continue

            # Normalize time format
            gametime_str = str(gametime)
            if len(gametime_str) == 5:
                gametime_str = f"{gametime_str}:00"

            kickoff = datetime.fromisoformat(f"{gameday}T{gametime_str}")

            home_score = row.get("home_score")
            away_score = row.get("away_score")

            winning_team = None
            is_tie = False

            if home_score is not None and away_score is not None:
                if home_score > away_score:
                    winning_team = row["home_team"]
                elif away_score > home_score:
                    winning_team = row["away_team"]
                else:
                    is_tie = True

            result = db.execute(
                text("""
                    insert into games (
                        week_id,
                        kickoff_at,
                        away_team,
                        home_team,
                        status,
                        away_score,
                        home_score,
                        winning_team,
                        is_tie
                    )
                    values (
                        :week_id,
                        :kickoff_at,
                        :away_team,
                        :home_team,
                        :status,
                        :away_score,
                        :home_score,
                        :winning_team,
                        :is_tie
                    )
                    on conflict (week_id, away_team, home_team, kickoff_at) do nothing
                    returning id
                """),
                {
                    "week_id": week_id,
                    "kickoff_at": kickoff,
                    "away_team": row["away_team"],
                    "home_team": row["home_team"],
                    "status": "final" if home_score is not None else "scheduled",
                    "away_score": away_score,
                    "home_score": home_score,
                    "winning_team": winning_team,
                    "is_tie": is_tie,
                }
            ).fetchone()

            if result:
                inserted_games += 1

        db.commit()

        return {
            "status": "import complete",
            "season_year": season_year,
            "weeks_created_or_found": len(week_map),
            "games_inserted": inserted_games,
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()