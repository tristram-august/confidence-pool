from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from uuid import uuid4
import nflreadpy as nfl
from datetime import datetime, timezone
from app.db import engine, SessionLocal
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEV_DISABLE_LOCKS = True

def get_game_count_for_week(db, week_id: str) -> int:
    result = db.execute(
        text("""
            select count(*) as game_count
            from games
            where week_id = :week_id
        """),
        {"week_id": week_id}
    ).fetchone()

    return int(result.game_count)

def get_allowed_confidence_values(game_count: int) -> list[int]:
    min_confidence = 17 - game_count
    max_confidence = 16
    return list(range(min_confidence, max_confidence + 1))

def score_pick_row(game_status, winning_team, is_tie, selected_team, confidence_value):
    """
    Returns:
        is_correct, points_awarded, result_bucket

    result_bucket is one of:
        "correct", "incorrect", "push", "void"
    """
    # canceled / void / postponed → no points
    if game_status in {"void", "cancelled", "postponed"}:
        return None, 0, "void"

    # tie game → push
    if is_tie:
        return None, 0, "push"

    # no final winner yet → not scoreable
    if winning_team is None:
        return None, 0, "void"

    # normal scoring
    if selected_team == winning_team:
        return True, confidence_value, "correct"

    return False, 0, "incorrect"

def rebuild_season_standings(db, pool_id: str):
    # wipe existing standings for this pool and rebuild from weekly_scores
    db.execute(
        text("""
            delete from season_standings
            where pool_id = :pool_id
        """),
        {"pool_id": pool_id}
    )

    db.execute(
        text("""
            insert into season_standings (
                pool_id,
                user_id,
                total_points,
                total_correct_picks,
                total_incorrect_picks,
                total_pushed_picks,
                total_voided_picks,
                highest_single_week_score
            )
            select
                ws.pool_id,
                ws.user_id,
                sum(ws.total_points) as total_points,
                sum(ws.correct_picks) as total_correct_picks,
                sum(ws.incorrect_picks) as total_incorrect_picks,
                sum(ws.pushed_picks) as total_pushed_picks,
                sum(ws.voided_picks) as total_voided_picks,
                max(ws.total_points) as highest_single_week_score
            from weekly_scores ws
            where ws.pool_id = :pool_id
            group by ws.pool_id, ws.user_id
        """),
        {"pool_id": pool_id}
    )

    standings = db.execute(
        text("""
            select id, user_id, total_points, total_correct_picks, highest_single_week_score
            from season_standings
            where pool_id = :pool_id
            order by
                total_points desc,
                total_correct_picks desc,
                highest_single_week_score desc,
                user_id asc
        """),
        {"pool_id": pool_id}
    ).fetchall()

    for idx, row in enumerate(standings, start=1):
        db.execute(
            text("""
                update season_standings
                set current_rank = :rank,
                    updated_at = now()
                where id = :id
            """),
            {"rank": idx, "id": row.id}
        )

def is_game_locked(db, game_id: str) -> bool:
    if DEV_DISABLE_LOCKS:
        return False

    game = db.execute(
        text("""
            select g.kickoff_at, g.week_id
            from games g
            where g.id = :game_id
        """),
        {"game_id": game_id}
    ).fetchone()

    if not game:
        return True

    now = datetime.now(timezone.utc)

    if game.kickoff_at <= now:
        return True

    sunday_lock = db.execute(
        text("""
            select min(g.kickoff_at) as sunday_1pm_lock
            from games g
            where g.week_id = :week_id
              and extract(dow from g.kickoff_at) = 0
              and extract(hour from g.kickoff_at) = 13
        """),
        {"week_id": game.week_id}
    ).fetchone()

    if sunday_lock and sunday_lock.sunday_1pm_lock:
        if now >= sunday_lock.sunday_1pm_lock:
            return True

    return False

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

        upserted_games = 0

        # --- Insert/update games ---
        for row in df.iter_rows(named=True):
            week_number = int(row["week"])
            week_id = week_map[week_number]

            gameday = row["gameday"]
            gametime = row["gametime"]

            if gameday is None or gametime is None:
                continue

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

            db.execute(
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
                    on conflict (week_id, away_team, home_team, kickoff_at)
                    do update set
                        status = excluded.status,
                        away_score = excluded.away_score,
                        home_score = excluded.home_score,
                        winning_team = excluded.winning_team,
                        is_tie = excluded.is_tie
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
            )

            upserted_games += 1

        db.commit()

        return {
            "status": "import complete",
            "season_year": season_year,
            "weeks_created_or_found": len(week_map),
            "games_upserted": upserted_games,
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()
        
@app.post("/pools/{pool_id}/weeks/{week_id}/submissions")
def create_submission(pool_id: str, week_id: str, user_id: str):
    db = SessionLocal()
    try:
        # Ensure user is a member of the pool
        member = db.execute(
            text("""
                select 1
                from pool_members
                where pool_id = :pool_id
                  and user_id = :user_id
            """),
            {"pool_id": pool_id, "user_id": user_id}
        ).fetchone()

        if not member:
            raise HTTPException(status_code=400, detail="User is not a member of this pool")

        # Ensure week exists
        week = db.execute(
            text("""
                select id
                from weeks
                where id = :week_id
            """),
            {"week_id": week_id}
        ).fetchone()

        if not week:
            raise HTTPException(status_code=404, detail="Week not found")

        existing = db.execute(
            text("""
                select id, pool_id, user_id, week_id, status, submitted_at
                from submissions
                where pool_id = :pool_id
                  and user_id = :user_id
                  and week_id = :week_id
            """),
            {
                "pool_id": pool_id,
                "user_id": user_id,
                "week_id": week_id
            }
        ).fetchone()

        if existing:
            return {
                "id": str(existing.id),
                "pool_id": str(existing.pool_id),
                "user_id": str(existing.user_id),
                "week_id": str(existing.week_id),
                "status": existing.status,
                "submitted_at": existing.submitted_at.isoformat() if existing.submitted_at else None
            }

        created = db.execute(
            text("""
                insert into submissions (pool_id, user_id, week_id)
                values (:pool_id, :user_id, :week_id)
                returning id, pool_id, user_id, week_id, status, submitted_at
            """),
            {
                "pool_id": pool_id,
                "user_id": user_id,
                "week_id": week_id
            }
        ).fetchone()

        db.commit()

        return {
            "id": str(created.id),
            "pool_id": str(created.pool_id),
            "user_id": str(created.user_id),
            "week_id": str(created.week_id),
            "status": created.status,
            "submitted_at": created.submitted_at.isoformat() if created.submitted_at else None
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()
        
@app.post("/submissions/{submission_id}/picks")
def save_pick(
    submission_id: str,
    game_id: str,
    selected_team: str,
    confidence_value: int
):
    db = SessionLocal()
    try:
        submission = db.execute(
            text("""
                select id, week_id, status
                from submissions
                where id = :submission_id
            """),
            {"submission_id": submission_id}
        ).fetchone()

        if not submission:
            raise HTTPException(status_code=404, detail="Submission not found")

        if submission.status == "submitted":
            raise HTTPException(status_code=400, detail="Submission already submitted")

        game = db.execute(
            text("""
                select id, week_id, away_team, home_team
                from games
                where id = :game_id
            """),
            {"game_id": game_id}
        ).fetchone()

        if not game:
            raise HTTPException(status_code=404, detail="Game not found")

        if str(game.week_id) != str(submission.week_id):
            raise HTTPException(status_code=400, detail="Game does not belong to submission week")

        if is_game_locked(db, game_id):
            raise HTTPException(
                status_code=400,
                detail="This game is locked and cannot be edited"
            )

        if selected_team not in {game.away_team, game.home_team}:
            raise HTTPException(
                status_code=400,
                detail=f"selected_team must be one of: {game.away_team}, {game.home_team}"
            )

        game_count = get_game_count_for_week(db, str(submission.week_id))
        allowed_values = get_allowed_confidence_values(game_count)

        if confidence_value not in allowed_values:
            raise HTTPException(
                status_code=400,
                detail=f"confidence_value must be in {allowed_values}"
            )

        existing_pick = db.execute(
            text("""
                select id
                from picks
                where submission_id = :submission_id
                  and game_id = :game_id
            """),
            {
                "submission_id": submission_id,
                "game_id": game_id
            }
        ).fetchone()

        if existing_pick:
            db.execute(
                text("""
                    update picks
                    set selected_team = :selected_team,
                        confidence_value = :confidence_value,
                        updated_at = now()
                    where id = :pick_id
                """),
                {
                    "pick_id": existing_pick.id,
                    "selected_team": selected_team,
                    "confidence_value": confidence_value
                }
            )
        else:
            db.execute(
                text("""
                    insert into picks (submission_id, game_id, selected_team, confidence_value)
                    values (:submission_id, :game_id, :selected_team, :confidence_value)
                """),
                {
                    "submission_id": submission_id,
                    "game_id": game_id,
                    "selected_team": selected_team,
                    "confidence_value": confidence_value
                }
            )

        db.commit()

        return {
            "message": "pick saved",
            "submission_id": submission_id,
            "game_id": game_id,
            "selected_team": selected_team,
            "confidence_value": confidence_value
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        error_text = str(e)

        if "picks_submission_id_confidence_value_key" in error_text:
            raise HTTPException(status_code=400, detail="Confidence value already used in this submission")

        if "picks_submission_id_game_id_key" in error_text:
            raise HTTPException(status_code=400, detail="Game already has a pick in this submission")

        raise HTTPException(status_code=400, detail=error_text)
    finally:
        db.close()
        
@app.get("/pools/{pool_id}/weeks/{week_id}/submissions/{user_id}")
def get_submission(pool_id: str, week_id: str, user_id: str):
    db = SessionLocal()
    try:
        submission = db.execute(
            text("""
                select id, pool_id, user_id, week_id, status, submitted_at
                from submissions
                where pool_id = :pool_id
                  and week_id = :week_id
                  and user_id = :user_id
            """),
            {
                "pool_id": pool_id,
                "week_id": week_id,
                "user_id": user_id
            }
        ).fetchone()

        if not submission:
            raise HTTPException(status_code=404, detail="Submission not found")

        picks_result = db.execute(
            text("""
                select
                    p.id,
                    p.game_id,
                    p.selected_team,
                    p.confidence_value,
                    g.away_team,
                    g.home_team,
                    g.kickoff_at
                from picks p
                join games g on p.game_id = g.id
                where p.submission_id = :submission_id
                order by g.kickoff_at asc, g.away_team asc, g.home_team asc
            """),
            {"submission_id": submission.id}
        )

        picks = []
        for row in picks_result:
            picks.append({
                "id": str(row.id),
                "game_id": str(row.game_id),
                "selected_team": row.selected_team,
                "confidence_value": row.confidence_value,
                "away_team": row.away_team,
                "home_team": row.home_team,
                "kickoff_at": row.kickoff_at.isoformat()
            })

        game_count = get_game_count_for_week(db, week_id)
        allowed_values = get_allowed_confidence_values(game_count)

        return {
            "submission": {
                "id": str(submission.id),
                "pool_id": str(submission.pool_id),
                "user_id": str(submission.user_id),
                "week_id": str(submission.week_id),
                "status": submission.status,
                "submitted_at": submission.submitted_at.isoformat() if submission.submitted_at else None
            },
            "game_count": game_count,
            "allowed_confidence_values": allowed_values,
            "picks": picks
        }

    finally:
        db.close()
        
@app.post("/submissions/{submission_id}/submit")
def submit_submission(submission_id: str):
    db = SessionLocal()
    try:
        submission = db.execute(
            text("""
                select id, week_id, status, tiebreaker_prediction
                from submissions
                where id = :submission_id
            """),
            {"submission_id": submission_id}
        ).fetchone()

        if not submission:
            raise HTTPException(status_code=404, detail="Submission not found")

        if submission.status == "submitted":
            raise HTTPException(status_code=400, detail="Submission already submitted")

        if submission.tiebreaker_prediction is None:
            raise HTTPException(
                status_code=400,
                detail="Tiebreaker prediction is required"
            )

        # Once any game in the week has started, no submission allowed
        lock_check = db.execute(
            text("""
                select 1
                from games
                where week_id = :week_id
                  and kickoff_at <= now()
                limit 1
            """),
            {"week_id": submission.week_id}
        ).fetchone()

        if lock_check:
            raise HTTPException(
                status_code=400,
                detail="Cannot submit after games have started"
            )

        game_count = get_game_count_for_week(db, str(submission.week_id))
        allowed_values = set(get_allowed_confidence_values(game_count))

        picks_result = db.execute(
            text("""
                select game_id, confidence_value
                from picks
                where submission_id = :submission_id
            """),
            {"submission_id": submission_id}
        )

        picks = picks_result.fetchall()

        if len(picks) != game_count:
            raise HTTPException(
                status_code=400,
                detail=f"Submission must contain picks for all {game_count} games"
            )

        used_game_ids = {str(row.game_id) for row in picks}
        if len(used_game_ids) != game_count:
            raise HTTPException(status_code=400, detail="Duplicate game picks detected")

        used_confidence_values = {row.confidence_value for row in picks}
        if used_confidence_values != allowed_values:
            raise HTTPException(
                status_code=400,
                detail=f"Submission must use each confidence value exactly once: {sorted(allowed_values)}"
            )

        db.execute(
            text("""
                update submissions
                set status = 'submitted',
                    submitted_at = now(),
                    updated_at = now()
                where id = :submission_id
            """),
            {"submission_id": submission_id}
        )

        db.commit()

        return {
            "message": "submission submitted",
            "submission_id": submission_id,
            "game_count": game_count,
            "confidence_values_used": sorted(list(used_confidence_values)),
            "tiebreaker_prediction": submission.tiebreaker_prediction
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()
        
@app.post("/admin/pools/{pool_id}/weeks/{week_id}/score")
def score_week(pool_id: str, week_id: str):
    db = SessionLocal()
    try:
        submissions = db.execute(
            text("""
                select id, user_id, tiebreaker_prediction
                from submissions
                where pool_id = :pool_id
                  and week_id = :week_id
                  and status = 'submitted'
            """),
            {"pool_id": pool_id, "week_id": week_id}
        ).fetchall()

        if not submissions:
            raise HTTPException(
                status_code=404,
                detail="No submitted submissions found for this pool/week"
            )

        # Find Monday Night Football game for this week
        mnf_game = db.execute(
            text("""
                select id, home_score, away_score
                from games
                where week_id = :week_id
                  and extract(dow from kickoff_at) = 1
                order by kickoff_at desc
                limit 1
            """),
            {"week_id": week_id}
        ).fetchone()

        mnf_total = None
        if mnf_game and mnf_game.home_score is not None and mnf_game.away_score is not None:
            mnf_total = mnf_game.home_score + mnf_game.away_score

        # reset existing weekly scores for this pool/week
        db.execute(
            text("""
                delete from weekly_scores
                where pool_id = :pool_id
                  and week_id = :week_id
            """),
            {"pool_id": pool_id, "week_id": week_id}
        )

        scored_users = 0

        for submission in submissions:
            picks = db.execute(
                text("""
                    select
                        p.id as pick_id,
                        p.selected_team,
                        p.confidence_value,
                        g.status as game_status,
                        g.winning_team,
                        g.is_tie
                    from picks p
                    join games g on p.game_id = g.id
                    where p.submission_id = :submission_id
                """),
                {"submission_id": submission.id}
            ).fetchall()

            correct_picks = 0
            incorrect_picks = 0
            pushed_picks = 0
            voided_picks = 0
            total_points = 0

            for pick in picks:
                is_correct, points_awarded, bucket = score_pick_row(
                    pick.game_status,
                    pick.winning_team,
                    pick.is_tie,
                    pick.selected_team,
                    pick.confidence_value
                )

                if bucket == "correct":
                    correct_picks += 1
                elif bucket == "incorrect":
                    incorrect_picks += 1
                elif bucket == "push":
                    pushed_picks += 1
                elif bucket == "void":
                    voided_picks += 1

                total_points += points_awarded

                db.execute(
                    text("""
                        update picks
                        set is_correct = :is_correct,
                            points_awarded = :points_awarded,
                            updated_at = now()
                        where id = :pick_id
                    """),
                    {
                        "pick_id": pick.pick_id,
                        "is_correct": is_correct,
                        "points_awarded": points_awarded
                    }
                )

            db.execute(
                text("""
                    insert into weekly_scores (
                        pool_id,
                        user_id,
                        week_id,
                        correct_picks,
                        incorrect_picks,
                        pushed_picks,
                        voided_picks,
                        total_points
                    )
                    values (
                        :pool_id,
                        :user_id,
                        :week_id,
                        :correct_picks,
                        :incorrect_picks,
                        :pushed_picks,
                        :voided_picks,
                        :total_points
                    )
                """),
                {
                    "pool_id": pool_id,
                    "user_id": submission.user_id,
                    "week_id": week_id,
                    "correct_picks": correct_picks,
                    "incorrect_picks": incorrect_picks,
                    "pushed_picks": pushed_picks,
                    "voided_picks": voided_picks,
                    "total_points": total_points
                }
            )

            scored_users += 1

        # assign weekly ranks, using MNF tiebreaker if available
        if mnf_total is not None:
            weekly_rows = db.execute(
                text("""
                    select
                        ws.id,
                        ws.user_id,
                        ws.total_points,
                        ws.correct_picks,
                        s.tiebreaker_prediction,
                        abs(s.tiebreaker_prediction - :mnf_total) as tiebreak_diff
                    from weekly_scores ws
                    join submissions s
                      on s.pool_id = ws.pool_id
                     and s.user_id = ws.user_id
                     and s.week_id = ws.week_id
                    where ws.pool_id = :pool_id
                      and ws.week_id = :week_id
                    order by
                        ws.total_points desc,
                        ws.correct_picks desc,
                        abs(s.tiebreaker_prediction - :mnf_total) asc,
                        ws.user_id asc
                """),
                {
                    "pool_id": pool_id,
                    "week_id": week_id,
                    "mnf_total": mnf_total
                }
            ).fetchall()
        else:
            weekly_rows = db.execute(
                text("""
                    select
                        ws.id,
                        ws.user_id,
                        ws.total_points,
                        ws.correct_picks,
                        s.tiebreaker_prediction,
                        null as tiebreak_diff
                    from weekly_scores ws
                    join submissions s
                      on s.pool_id = ws.pool_id
                     and s.user_id = ws.user_id
                     and s.week_id = ws.week_id
                    where ws.pool_id = :pool_id
                      and ws.week_id = :week_id
                    order by
                        ws.total_points desc,
                        ws.correct_picks desc,
                        ws.user_id asc
                """),
                {
                    "pool_id": pool_id,
                    "week_id": week_id
                }
            ).fetchall()

        for idx, row in enumerate(weekly_rows, start=1):
            db.execute(
                text("""
                    update weekly_scores
                    set weekly_rank = :rank,
                        updated_at = now()
                    where id = :id
                """),
                {"rank": idx, "id": row.id}
            )

        rebuild_season_standings(db, pool_id)

        db.commit()

        return {
            "message": "week scored",
            "pool_id": pool_id,
            "week_id": week_id,
            "users_scored": scored_users,
            "mnf_total": mnf_total
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()
        
@app.get("/pools/{pool_id}/weeks/{week_id}/leaderboard")
def get_weekly_leaderboard(pool_id: str, week_id: str):
    db = SessionLocal()
    try:
        mnf_game = db.execute(
            text("""
                select id, home_score, away_score
                from games
                where week_id = :week_id
                  and extract(dow from kickoff_at) = 1
                order by kickoff_at desc
                limit 1
            """),
            {"week_id": week_id}
        ).fetchone()

        mnf_total = None
        if mnf_game and mnf_game.home_score is not None and mnf_game.away_score is not None:
            mnf_total = mnf_game.home_score + mnf_game.away_score

        if mnf_total is not None:
            rows = db.execute(
                text("""
                    select
                        ws.weekly_rank,
                        ws.user_id,
                        u.display_name,
                        ws.total_points,
                        ws.correct_picks,
                        ws.incorrect_picks,
                        ws.pushed_picks,
                        ws.voided_picks,
                        s.tiebreaker_prediction,
                        abs(s.tiebreaker_prediction - :mnf_total) as tiebreak_diff
                    from weekly_scores ws
                    join users u on ws.user_id = u.id
                    join submissions s
                      on s.pool_id = ws.pool_id
                     and s.user_id = ws.user_id
                     and s.week_id = ws.week_id
                    where ws.pool_id = :pool_id
                      and ws.week_id = :week_id
                    order by ws.weekly_rank asc, u.display_name asc
                """),
                {
                    "pool_id": pool_id,
                    "week_id": week_id,
                    "mnf_total": mnf_total
                }
            ).fetchall()
        else:
            rows = db.execute(
                text("""
                    select
                        ws.weekly_rank,
                        ws.user_id,
                        u.display_name,
                        ws.total_points,
                        ws.correct_picks,
                        ws.incorrect_picks,
                        ws.pushed_picks,
                        ws.voided_picks,
                        s.tiebreaker_prediction,
                        null as tiebreak_diff
                    from weekly_scores ws
                    join users u on ws.user_id = u.id
                    join submissions s
                      on s.pool_id = ws.pool_id
                     and s.user_id = ws.user_id
                     and s.week_id = ws.week_id
                    where ws.pool_id = :pool_id
                      and ws.week_id = :week_id
                    order by ws.weekly_rank asc, u.display_name asc
                """),
                {
                    "pool_id": pool_id,
                    "week_id": week_id
                }
            ).fetchall()

        return {
            "week_id": week_id,
            "mnf_total": mnf_total,
            "leaderboard": [
                {
                    "weekly_rank": row.weekly_rank,
                    "user_id": str(row.user_id),
                    "display_name": row.display_name,
                    "total_points": row.total_points,
                    "correct_picks": row.correct_picks,
                    "incorrect_picks": row.incorrect_picks,
                    "pushed_picks": row.pushed_picks,
                    "voided_picks": row.voided_picks,
                    "tiebreaker_prediction": row.tiebreaker_prediction,
                    "tiebreak_diff": row.tiebreak_diff
                }
                for row in rows
            ]
        }

    finally:
        db.close()
        
@app.get("/pools/{pool_id}/standings")
def get_season_standings(pool_id: str):
    db = SessionLocal()
    try:
        rows = db.execute(
            text("""
                select
                    ss.current_rank,
                    ss.user_id,
                    u.display_name,
                    ss.total_points,
                    ss.total_correct_picks,
                    ss.total_incorrect_picks,
                    ss.total_pushed_picks,
                    ss.total_voided_picks,
                    ss.highest_single_week_score
                from season_standings ss
                join users u on ss.user_id = u.id
                where ss.pool_id = :pool_id
                order by ss.current_rank asc, u.display_name asc
            """),
            {"pool_id": pool_id}
        ).fetchall()

        return [
            {
                "current_rank": row.current_rank,
                "user_id": str(row.user_id),
                "display_name": row.display_name,
                "total_points": row.total_points,
                "record": f"{row.total_correct_picks}-{row.total_incorrect_picks}",
                "total_correct_picks": row.total_correct_picks,
                "total_incorrect_picks": row.total_incorrect_picks,
                "total_pushed_picks": row.total_pushed_picks,
                "total_voided_picks": row.total_voided_picks,
                "highest_single_week_score": row.highest_single_week_score
            }
            for row in rows
        ]

    finally:
        db.close()
        
@app.post("/submissions/{submission_id}/tiebreaker")
def set_tiebreaker(submission_id: str, prediction: int):
    db = SessionLocal()
    try:
        submission = db.execute(
            text("""
                select id, status
                from submissions
                where id = :submission_id
            """),
            {"submission_id": submission_id}
        ).fetchone()

        if not submission:
            raise HTTPException(status_code=404, detail="Submission not found")

        if submission.status == "submitted":
            raise HTTPException(status_code=400, detail="Submission already submitted")

        db.execute(
            text("""
                update submissions
                set tiebreaker_prediction = :prediction,
                    updated_at = now()
                where id = :submission_id
            """),
            {
                "submission_id": submission_id,
                "prediction": prediction
            }
        )

        db.commit()

        return {
            "message": "tiebreaker set",
            "submission_id": submission_id,
            "prediction": prediction
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()
        
@app.get("/pools/{pool_id}/weeks/{week_id}/games")
def get_pool_week_games(pool_id: str, week_id: str, user_id: str | None = None):
    db = SessionLocal()
    try:
        # validate pool exists
        pool = db.execute(
            text("""
                select id, name, season_year
                from pools
                where id = :pool_id
            """),
            {"pool_id": pool_id}
        ).fetchone()

        if not pool:
            raise HTTPException(status_code=404, detail="Pool not found")

        # validate week exists
        week = db.execute(
            text("""
                select id, season_year, week_number, week_type
                from weeks
                where id = :week_id
            """),
            {"week_id": week_id}
        ).fetchone()

        if not week:
            raise HTTPException(status_code=404, detail="Week not found")

        submission_id = None
        submission_status = None
        picks_by_game_id = {}

        if user_id:
            submission = db.execute(
                text("""
                    select id, status
                    from submissions
                    where pool_id = :pool_id
                      and week_id = :week_id
                      and user_id = :user_id
                """),
                {
                    "pool_id": pool_id,
                    "week_id": week_id,
                    "user_id": user_id
                }
            ).fetchone()

            if submission:
                submission_id = str(submission.id)

                picks = db.execute(
                    text("""
                        select game_id, selected_team, confidence_value
                        from picks
                        where submission_id = :submission_id
                    """),
                    {"submission_id": submission.id}
                ).fetchall()

                picks_by_game_id = {
                    str(row.game_id): {
                        "selected_team": row.selected_team,
                        "confidence_value": row.confidence_value
                    }
                    for row in picks
                }

        games = db.execute(
            text("""
                select
                    id,
                    away_team,
                    home_team,
                    kickoff_at,
                    status,
                    away_score,
                    home_score,
                    winning_team,
                    is_tie
                from games
                where week_id = :week_id
                order by kickoff_at asc, away_team asc, home_team asc
            """),
            {"week_id": week_id}
        ).fetchall()

        response_games = []
        for game in games:
            game_id = str(game.id)
            existing_pick = picks_by_game_id.get(game_id)

            response_games.append({
                "game_id": game_id,
                "away_team": game.away_team,
                "home_team": game.home_team,
                "kickoff_at": game.kickoff_at.isoformat() if game.kickoff_at else None,
                "status": game.status,
                "away_score": game.away_score,
                "home_score": game.home_score,
                "winning_team": game.winning_team,
                "is_tie": game.is_tie,
                "is_locked": is_game_locked(db, game_id),
                "selected_team": existing_pick["selected_team"] if existing_pick else None,
                "confidence_value": existing_pick["confidence_value"] if existing_pick else None
            })

        game_count = len(response_games)
        allowed_confidence_values = get_allowed_confidence_values(game_count)

        return {
            "pool": {
                "id": str(pool.id),
                "name": pool.name,
                "season_year": pool.season_year
            },
            "week": {
                "id": str(week.id),
                "season_year": week.season_year,
                "week_number": week.week_number,
                "week_type": week.week_type
            },
            "submission_id": submission_id,
            "submission_status": submission_status,
            "game_count": game_count,
            "allowed_confidence_values": allowed_confidence_values,
            "games": response_games
        }

    finally:
        db.close()