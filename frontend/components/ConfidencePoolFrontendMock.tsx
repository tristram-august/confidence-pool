export default function ConfidencePoolFrontendMock() {
  const pool = {
    name: "Tristram Confidence Pool",
    season: 2025,
    week: 1,
    members: 12,
  };

  const weeklyLeaderboard = [
    { rank: 1, name: "AugustTheWeek", points: 104, record: "12-4", tiebreak: 3 },
    { rank: 2, name: "Megan", points: 104, record: "12-4", tiebreak: 7 },
    { rank: 3, name: "Dan", points: 97, record: "11-5", tiebreak: 10 },
    { rank: 4, name: "Chris", points: 89, record: "10-6", tiebreak: 14 },
  ];

  const seasonStandings = [
    { rank: 1, name: "AugustTheWeek", points: 104, record: "12-4", highWeek: 104 },
    { rank: 2, name: "Megan", points: 104, record: "12-4", highWeek: 104 },
    { rank: 3, name: "Dan", points: 97, record: "11-5", highWeek: 97 },
    { rank: 4, name: "Chris", points: 89, record: "10-6", highWeek: 89 },
  ];

  const games = [
    { away: "DAL", home: "PHI", kickoff: "Thu 8:15 PM", pick: "PHI", confidence: 16, locked: true },
    { away: "BUF", home: "MIA", kickoff: "Sun 1:00 PM", pick: "BUF", confidence: 15, locked: false },
    { away: "KC", home: "LAC", kickoff: "Sun 4:25 PM", pick: "KC", confidence: 14, locked: false },
    { away: "BAL", home: "CIN", kickoff: "Mon 8:15 PM", pick: "BAL", confidence: 13, locked: false },
  ];

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        <header className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-4xl font-bold tracking-tight">Confidence Pool</h1>
            <p className="text-slate-600 mt-1">A clean commissioner-first NFL confidence pool experience.</p>
          </div>
          <div className="flex gap-3">
            <button className="px-4 py-2 rounded-2xl bg-slate-900 text-white shadow">My Picks</button>
            <button className="px-4 py-2 rounded-2xl bg-white border shadow-sm">Weekly Results</button>
            <button className="px-4 py-2 rounded-2xl bg-white border shadow-sm">Season Standings</button>
          </div>
        </header>

        <section className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-white rounded-2xl shadow-sm border p-5">
            <div className="text-sm text-slate-500">Pool</div>
            <div className="text-xl font-semibold mt-1">{pool.name}</div>
          </div>
          <div className="bg-white rounded-2xl shadow-sm border p-5">
            <div className="text-sm text-slate-500">Season</div>
            <div className="text-xl font-semibold mt-1">{pool.season}</div>
          </div>
          <div className="bg-white rounded-2xl shadow-sm border p-5">
            <div className="text-sm text-slate-500">Current Week</div>
            <div className="text-xl font-semibold mt-1">Week {pool.week}</div>
          </div>
          <div className="bg-white rounded-2xl shadow-sm border p-5">
            <div className="text-sm text-slate-500">Members</div>
            <div className="text-xl font-semibold mt-1">{pool.members}</div>
          </div>
        </section>

        <section className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          <div className="xl:col-span-2 bg-white rounded-2xl shadow-sm border p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-2xl font-semibold">Week {pool.week} Picks</h2>
                <p className="text-slate-500 text-sm mt-1">Locked games are read-only. Remaining games stay editable until Sunday 1 PM ET.</p>
              </div>
              <button className="px-4 py-2 rounded-2xl bg-slate-900 text-white shadow">Submit Picks</button>
            </div>

            <div className="space-y-3">
              {games.map((game, idx) => (
                <div key={idx} className="rounded-2xl border p-4 bg-slate-50">
                  <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
                    <div>
                      <div className="font-semibold text-lg">{game.away} @ {game.home}</div>
                      <div className="text-sm text-slate-500">{game.kickoff}</div>
                    </div>
                    <div className="flex flex-wrap items-center gap-3">
                      <select
                        className="px-3 py-2 rounded-xl border bg-white"
                        defaultValue={game.pick}
                        disabled={game.locked}
                      >
                        <option value={game.away}>{game.away}</option>
                        <option value={game.home}>{game.home}</option>
                      </select>
                      <input
                        type="number"
                        className="w-24 px-3 py-2 rounded-xl border bg-white"
                        defaultValue={game.confidence}
                        disabled={game.locked}
                      />
                      <span className={`px-3 py-1 rounded-full text-sm ${game.locked ? "bg-slate-900 text-white" : "bg-white border text-slate-700"}`}>
                        {game.locked ? "Locked" : "Open"}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="space-y-6">
            <div className="bg-white rounded-2xl shadow-sm border p-5">
              <h2 className="text-xl font-semibold mb-4">Weekly Leaderboard</h2>
              <div className="space-y-3">
                {weeklyLeaderboard.map((row) => (
                  <div key={row.rank} className="flex items-center justify-between rounded-xl bg-slate-50 border p-3">
                    <div>
                      <div className="font-semibold">#{row.rank} {row.name}</div>
                      <div className="text-sm text-slate-500">Record {row.record} · Tiebreak diff {row.tiebreak}</div>
                    </div>
                    <div className="text-xl font-bold">{row.points}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="bg-white rounded-2xl shadow-sm border p-5">
              <h2 className="text-xl font-semibold mb-4">Season Standings</h2>
              <div className="space-y-3">
                {seasonStandings.map((row) => (
                  <div key={row.rank} className="flex items-center justify-between rounded-xl bg-slate-50 border p-3">
                    <div>
                      <div className="font-semibold">#{row.rank} {row.name}</div>
                      <div className="text-sm text-slate-500">{row.record} · High week {row.highWeek}</div>
                    </div>
                    <div className="text-xl font-bold">{row.points}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
