"use client";

import { useEffect, useMemo, useState } from "react";

type WeeklyLeaderboardRow = {
  weekly_rank: number;
  user_id: string;
  display_name: string;
  total_points: number;
  correct_picks: number;
  incorrect_picks: number;
  pushed_picks: number;
  voided_picks: number;
  tiebreaker_prediction: number | null;
  tiebreak_diff: number | null;
};

type WeeklyLeaderboardResponse = {
  week_id: string;
  mnf_total: number | null;
  leaderboard: WeeklyLeaderboardRow[];
};

type PoolWeekGame = {
  game_id: string;
  away_team: string;
  home_team: string;
  kickoff_at: string | null;
  status: string;
  away_score: number | null;
  home_score: number | null;
  winning_team: string | null;
  is_tie: boolean;
  is_locked: boolean;
  selected_team: string | null;
  confidence_value: number | null;
};

type PoolWeekGamesResponse = {
  pool: {
    id: string;
    name: string;
    season_year: number;
  };
  week: {
    id: string;
    season_year: number;
    week_number: number;
    week_type: string;
  };
  submission_id: string | null;
  game_count: number;
  allowed_confidence_values: number[];
  games: PoolWeekGame[];
};

const POOL_ID = "0f0fff2c-95de-4de8-9c1d-3a1b43b63b96";
const WEEK_ID = "f0cf48e6-7909-4515-a84a-eb4898e6e255";
const USER_ID = "de25982c-2dc3-4fbb-80a9-db08de31871e";

type EditableGameState = {
  game_id: string;
  selected_team: string;
  confidence_value: number | "";
};

export default function ConfidencePoolFrontendMock() {
  const [weeklyLeaderboard, setWeeklyLeaderboard] = useState<WeeklyLeaderboardRow[]>([]);
  const [mnfTotal, setMnfTotal] = useState<number | null>(null);
  const [loadingLeaderboard, setLoadingLeaderboard] = useState(true);
  const [leaderboardError, setLeaderboardError] = useState<string | null>(null);

  const [gamesPayload, setGamesPayload] = useState<PoolWeekGamesResponse | null>(null);
  const [loadingGames, setLoadingGames] = useState(true);
  const [gamesError, setGamesError] = useState<string | null>(null);

  const [editableGames, setEditableGames] = useState<Record<string, EditableGameState>>({});

  useEffect(() => {
    const fetchLeaderboard = async () => {
      try {
        setLoadingLeaderboard(true);
        setLeaderboardError(null);

        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_BASE_URL}/pools/${POOL_ID}/weeks/${WEEK_ID}/leaderboard`
        );

        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`Leaderboard request failed: ${response.status} ${errorText}`);
        }

        const data: WeeklyLeaderboardResponse = await response.json();

        setWeeklyLeaderboard(data.leaderboard ?? []);
        setMnfTotal(data.mnf_total ?? null);
      } catch (error) {
        console.error("Failed to load weekly leaderboard:", error);
        setLeaderboardError(
          error instanceof Error ? error.message : "Could not load weekly leaderboard."
        );
      } finally {
        setLoadingLeaderboard(false);
      }
    };

    fetchLeaderboard();
  }, []);

  useEffect(() => {
    const fetchGames = async () => {
      try {
        setLoadingGames(true);
        setGamesError(null);

        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_BASE_URL}/pools/${POOL_ID}/weeks/${WEEK_ID}/games?user_id=${USER_ID}`
        );

        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`Games request failed: ${response.status} ${errorText}`);
        }

        const data: PoolWeekGamesResponse = await response.json();
        setGamesPayload(data);

        const initialEditableState: Record<string, EditableGameState> = {};
        for (const game of data.games) {
          initialEditableState[game.game_id] = {
            game_id: game.game_id,
            selected_team: game.selected_team ?? game.home_team,
            confidence_value: game.confidence_value ?? "",
          };
        }
        setEditableGames(initialEditableState);
      } catch (error) {
        console.error("Failed to load week games:", error);
        setGamesError(
          error instanceof Error ? error.message : "Could not load games."
        );
      } finally {
        setLoadingGames(false);
      }
    };

    fetchGames();
  }, []);

  const poolName = gamesPayload?.pool.name ?? "Confidence Pool";
  const seasonYear = gamesPayload?.pool.season_year ?? 2025;
  const weekNumber = gamesPayload?.week.week_number ?? 1;
  const memberCount = weeklyLeaderboard.length || 0;
  const allowedConfidenceValues = gamesPayload?.allowed_confidence_values ?? [];

  const usedConfidenceValues = useMemo(() => {
    return Object.values(editableGames)
      .map((game) => game.confidence_value)
      .filter((value): value is number => typeof value === "number");
  }, [editableGames]);

  const duplicateConfidenceValues = useMemo(() => {
    const counts = new Map<number, number>();
    for (const value of usedConfidenceValues) {
      counts.set(value, (counts.get(value) ?? 0) + 1);
    }

    const duplicates = new Set<number>();
    for (const [value, count] of counts.entries()) {
      if (count > 1) {
        duplicates.add(value);
      }
    }

    return duplicates;
  }, [usedConfidenceValues]);

  const savePick = async (gameId: string, selectedTeam: string, confidenceValue: number) => {
    if (!gamesPayload?.submission_id) return;

    try {
        await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE_URL}/submissions/${gamesPayload.submission_id}/picks`,
        {
            method: "POST",
            headers: {
            "Content-Type": "application/json",
            },
            body: JSON.stringify({
            game_id: gameId,
            selected_team: selectedTeam,
            confidence_value: confidenceValue,
            }),
        }
        );
    } catch (err) {
        console.error("Failed to save pick", err);
    }
  };

  const [submitMessage, setSubmitMessage] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submitPicks = async () => {
    if (!gamesPayload?.submission_id) {
        setSubmitError("No submission found for this week.");
        return;
    }

    try {
        setSubmitting(true);
        setSubmitError(null);
        setSubmitMessage(null);

        const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE_URL}/submissions/${gamesPayload.submission_id}/submit`,
        {
            method: "POST",
        }
        );

        if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Submit failed: ${response.status} ${errorText}`);
        }

        const data = await response.json();
        setSubmitMessage(data.message ?? "Picks submitted successfully.");
    } catch (error) {
        console.error("Failed to submit picks:", error);
        setSubmitError(
        error instanceof Error ? error.message : "Could not submit picks."
        );
    } finally {
        setSubmitting(false);
    }
  };
  
  const handleTeamChange = (gameId: string, selectedTeam: string) => {
    setEditableGames((prev) => {
        const updated = {
        ...prev,
        [gameId]: {
            ...prev[gameId],
            selected_team: selectedTeam,
        },
        };

        const confidence = updated[gameId].confidence_value;
        if (confidence !== "") {
        savePick(gameId, selectedTeam, confidence as number);
        }

        return updated;
    });
  };

  const handleConfidenceChange = (gameId: string, rawValue: string) => {
    const parsed = rawValue === "" ? "" : Number(rawValue);

    setEditableGames((prev) => {
        const updated = {
        ...prev,
        [gameId]: {
            ...prev[gameId],
            confidence_value:
            parsed === "" || Number.isNaN(parsed) ? "" : parsed,
        },
        };

        const selectedTeam = updated[gameId].selected_team;
        if (parsed !== "" && selectedTeam) {
        savePick(gameId, selectedTeam, parsed as number);
        }

        return updated;
    });
  };
  const formatKickoff = (kickoffAt: string | null) => {
    if (!kickoffAt) return "TBD";

    const date = new Date(kickoffAt);

    return new Intl.DateTimeFormat("en-US", {
      weekday: "short",
      hour: "numeric",
      minute: "2-digit",
      timeZone: "America/New_York",
    }).format(date);
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        <header className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-4xl font-bold tracking-tight">Confidence Pool</h1>
            <p className="text-slate-600 mt-1">
              A clean commissioner-first NFL confidence pool experience.
            </p>
          </div>
          <div className="flex gap-3">
            <button className="px-4 py-2 rounded-2xl bg-slate-900 text-white shadow">
              My Picks
            </button>
            <button className="px-4 py-2 rounded-2xl bg-white border shadow-sm">
              Weekly Results
            </button>
            <button className="px-4 py-2 rounded-2xl bg-white border shadow-sm">
              Season Standings
            </button>
          </div>
        </header>

        <section className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-white rounded-2xl shadow-sm border p-5">
            <div className="text-sm text-slate-500">Pool</div>
            <div className="text-xl font-semibold mt-1">{poolName}</div>
          </div>
          <div className="bg-white rounded-2xl shadow-sm border p-5">
            <div className="text-sm text-slate-500">Season</div>
            <div className="text-xl font-semibold mt-1">{seasonYear}</div>
          </div>
          <div className="bg-white rounded-2xl shadow-sm border p-5">
            <div className="text-sm text-slate-500">Current Week</div>
            <div className="text-xl font-semibold mt-1">Week {weekNumber}</div>
          </div>
          <div className="bg-white rounded-2xl shadow-sm border p-5">
            <div className="text-sm text-slate-500">Members</div>
            <div className="text-xl font-semibold mt-1">{memberCount}</div>
          </div>
        </section>

        <section className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          <div className="xl:col-span-2 bg-white rounded-2xl shadow-sm border p-5">
            <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between mb-4">
              <div>
                <h2 className="text-2xl font-semibold">Week {weekNumber} Picks</h2>
                <p className="text-slate-500 text-sm mt-1">
                  Locked games are read-only. Remaining games stay editable until Sunday 1 PM ET.
                </p>
              </div>
              <div className="text-sm text-slate-500">
                Allowed confidence values:{" "}
                <span className="font-medium text-slate-900">
                  {allowedConfidenceValues.length > 0
                    ? allowedConfidenceValues.join(", ")
                    : "-"}
                </span>
              </div>
            </div>

            <div className="mb-4 flex flex-wrap items-center gap-3">
            <button
                className="px-4 py-2 rounded-2xl bg-slate-900 text-white shadow disabled:opacity-50"
                onClick={submitPicks}
                disabled={submitting || !gamesPayload?.submission_id}
            >
                {submitting ? "Submitting..." : "Submit Picks"}
            </button>
            {submitMessage && (
                <div className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-xl px-3 py-2">
                    {submitMessage}
                </div>
            )}

                {submitError && (
                <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-xl px-3 py-2">
                    {submitError}
                </div>
            )}
              {duplicateConfidenceValues.size > 0 && (
                <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-xl px-3 py-2">
                  Duplicate confidence values detected:{" "}
                  {Array.from(duplicateConfidenceValues).sort((a, b) => a - b).join(", ")}
                </div>
              )}
            </div>

            {loadingGames ? (
              <div className="rounded-xl bg-slate-50 border p-4 text-slate-500">
                Loading games...
              </div>
            ) : gamesError ? (
              <div className="rounded-xl bg-red-50 border border-red-200 p-4 text-red-700">
                {gamesError}
              </div>
            ) : !gamesPayload || gamesPayload.games.length === 0 ? (
              <div className="rounded-xl bg-slate-50 border p-4 text-slate-500">
                No games found for this week.
              </div>
            ) : (
              <div className="space-y-3">
                {gamesPayload.games.map((game) => {
                  const editable = editableGames[game.game_id];
                  const hasDuplicateConfidence =
                    typeof editable?.confidence_value === "number" &&
                    duplicateConfidenceValues.has(editable.confidence_value);

                  return (
                    <div key={game.game_id} className="rounded-2xl border p-4 bg-slate-50">
                      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
                        <div>
                          <div className="font-semibold text-lg">
                            {game.away_team} @ {game.home_team}
                          </div>
                          <div className="text-sm text-slate-500">
                            {formatKickoff(game.kickoff_at)}
                          </div>

                          {game.status === "final" && (
                            <div className="text-sm text-slate-600 mt-1">
                              Final: {game.away_team} {game.away_score} - {game.home_team}{" "}
                              {game.home_score}
                              {game.winning_team && (
                                <span className="ml-2 font-medium text-slate-900">
                                  Winner: {game.winning_team}
                                </span>
                              )}
                              {game.is_tie && (
                                <span className="ml-2 font-medium text-slate-900">Tie</span>
                              )}
                            </div>
                          )}
                        </div>

                        <div className="flex flex-wrap items-center gap-3">
                          <select
                            className="px-3 py-2 rounded-xl border bg-white disabled:bg-slate-100 disabled:text-slate-500"
                            value={editable?.selected_team ?? game.home_team}
                            disabled={game.is_locked}
                            onChange={(e) => handleTeamChange(game.game_id, e.target.value)}
                          >
                            <option value={game.away_team}>{game.away_team}</option>
                            <option value={game.home_team}>{game.home_team}</option>
                          </select>

                          <select
                            className={`px-3 py-2 rounded-xl border bg-white disabled:bg-slate-100 disabled:text-slate-500 ${
                              hasDuplicateConfidence ? "border-red-500" : ""
                            }`}
                            value={editable?.confidence_value === "" ? "" : editable?.confidence_value ?? ""}
                            disabled={game.is_locked}
                            onChange={(e) => handleConfidenceChange(game.game_id, e.target.value)}
                          >
                            <option value="">Confidence</option>
                            {allowedConfidenceValues.map((value) => (
                              <option key={value} value={value}>
                                {value}
                              </option>
                            ))}
                          </select>

                          <span
                            className={`px-3 py-1 rounded-full text-sm ${
                              game.is_locked
                                ? "bg-slate-900 text-white"
                                : "bg-white border text-slate-700"
                            }`}
                          >
                            {game.is_locked ? "Locked" : "Open"}
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="space-y-6">
            <div className="bg-white rounded-2xl shadow-sm border p-5">
              <div className="flex items-start justify-between mb-4 gap-4">
                <div>
                  <h2 className="text-xl font-semibold">Weekly Leaderboard</h2>
                  <p className="text-sm text-slate-500 mt-1">
                    Real data from your FastAPI backend
                  </p>
                </div>
                <div className="text-right text-sm text-slate-500">
                  <div>MNF Total</div>
                  <div className="font-semibold text-slate-900">{mnfTotal ?? "-"}</div>
                </div>
              </div>

              {loadingLeaderboard ? (
                <div className="rounded-xl bg-slate-50 border p-4 text-slate-500">
                  Loading leaderboard...
                </div>
              ) : leaderboardError ? (
                <div className="rounded-xl bg-red-50 border border-red-200 p-4 text-red-700">
                  {leaderboardError}
                </div>
              ) : weeklyLeaderboard.length === 0 ? (
                <div className="rounded-xl bg-slate-50 border p-4 text-slate-500">
                  No leaderboard data found for this week.
                </div>
              ) : (
                <div className="space-y-3">
                  {weeklyLeaderboard.map((row) => (
                    <div
                      key={row.user_id}
                      className="flex items-center justify-between rounded-xl bg-slate-50 border p-3"
                    >
                      <div>
                        <div className="font-semibold">
                          #{row.weekly_rank} {row.display_name}
                        </div>
                        <div className="text-sm text-slate-500">
                          Record {row.correct_picks}-{row.incorrect_picks}
                          {" · "}
                          Tiebreak diff {row.tiebreak_diff ?? "-"}
                        </div>
                      </div>
                      <div className="text-xl font-bold">{row.total_points}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="bg-white rounded-2xl shadow-sm border p-5">
              <h2 className="text-xl font-semibold mb-4">Week Snapshot</h2>
              <div className="space-y-3 text-sm text-slate-600">
                <div className="flex items-center justify-between rounded-xl bg-slate-50 border p-3">
                  <span>Submission ID</span>
                  <span className="font-medium text-slate-900">
                    {gamesPayload?.submission_id ?? "-"}
                  </span>
                </div>
                <div className="flex items-center justify-between rounded-xl bg-slate-50 border p-3">
                  <span>Games This Week</span>
                  <span className="font-medium text-slate-900">
                    {gamesPayload?.game_count ?? "-"}
                  </span>
                </div>
                <div className="flex items-center justify-between rounded-xl bg-slate-50 border p-3">
                  <span>Picked So Far</span>
                  <span className="font-medium text-slate-900">
                    {
                      Object.values(editableGames).filter(
                        (g) => g.selected_team && g.confidence_value !== ""
                      ).length
                    }
                  </span>
                </div>
                <div className="flex items-center justify-between rounded-xl bg-slate-50 border p-3">
                  <span>Duplicate Confidences</span>
                  <span className="font-medium text-slate-900">
                    {duplicateConfidenceValues.size}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}