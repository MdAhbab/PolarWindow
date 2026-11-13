<#
POLAR WINDOW: on the owner's Windows PC, make the bundle the VM starts from.

    powershell -ExecutionPolicy Bypass -File deploy\pc-export.ps1
    powershell -ExecutionPolicy Bypass -File deploy\pc-export.ps1 -OutDir D:\pw-deploy -NoLola

Run from the repository root while the local PostgreSQL (run.py, port 5432) is up.
It changes nothing in the repository or the database; it only reads them and writes
into OutDir (default: %USERPROFILE%\pw-deploy). docs/deploy-gcp.md, stage 0.

Writes:
  polar_window.dump        pg_dump -Fc of the local database (60 MB on 13 November)
  pw-data-core.tar         the data the running app reads that git does not carry
                           (kernels, terrain, tiles, gravity, DSN, space weather, flown
                           CLPS trajectories, weather caches, the Diviner index, the
                           PGDA illumination maps): 1.27 GB on 13 November
  pw-data-lola5m.tar       the 5 m LOLA tiles for the landing ellipse (1.54 GB); not
                           written with -NoLola (the app then falls back to its 20 m
                           terrain for the ellipse and says so)
  *.list                   what each tar holds
  catalogues.sha256        sha256 of data/catalogues/*.json as this PC has them (the
                           stored answers' keys depend on these bytes; the VM checks it)
  pc-info.txt              the commit, the migration, row counts, for the checks on the VM
  SHA256SUMS               sha256 of every file above, for `sha256sum -c` on the VM

Stops before writing anything if a compute job is still queued or running.
#>
[CmdletBinding()]
param(
    [string]$OutDir = (Join-Path $HOME 'pw-deploy'),
    [switch]$NoLola,
    [string]$PgBin = '',
    [string]$PgPassword = 'postgres'
)

$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $PgBin) { $PgBin = Join-Path $Repo '.local\tools\pgsql\bin' }
$psql = Join-Path $PgBin 'psql.exe'
$pgdump = Join-Path $PgBin 'pg_dump.exe'
$pgrestore = Join-Path $PgBin 'pg_restore.exe'
$tar = Join-Path $env:SystemRoot 'System32\tar.exe'
foreach ($exe in @($psql, $pgdump, $pgrestore, $tar)) {
    if (-not (Test-Path -LiteralPath $exe)) { throw "Not found: $exe" }
}

function Sql([string]$query) {
    $out = & $psql -h localhost -U postgres -d polar_window -At -c $query
    if ($LASTEXITCODE -ne 0) { throw "psql failed: $query" }
    return (($out | Out-String).Trim())
}
function Write-Lf([string]$path, [string[]]$lines) {
    $text = ($lines -join "`n") + "`n"
    [System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding $false))
}
function Sha([string]$path) {
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLower()
}
function Rel([System.IO.FileInfo]$f) {
    return $f.FullName.Substring($Repo.Length + 1).Replace('\', '/')
}

$env:PGPASSWORD = $PgPassword
try {
    Write-Host '== 0. checks (read only)'
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
    $OutDir = (Resolve-Path -LiteralPath $OutDir).Path
    if ($OutDir.StartsWith($Repo, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "OutDir must be outside the repository: $OutDir"
    }
    $drive = Get-PSDrive -Name ($OutDir.Substring(0, 1))
    if ($drive.Free -lt 4GB) { throw ('Less than 4 GB free on ' + $drive.Name + ':') }

    $busy = [int](Sql "select count(*) from jobs where status in ('queued','running')")
    if ($busy -ne 0) {
        throw "$busy compute jobs are still queued or running. Wait until they finish (the presets), then run this again."
    }
    $commit = (& git -C $Repo rev-parse HEAD | Out-String).Trim()
    $dirty = & git -C $Repo status --porcelain -- backend/app backend/alembic data/catalogues data/missions.json
    if ($dirty) {
        Write-Warning "Uncommitted changes in code or data the answers depend on:`n$($dirty -join "`n")`nThe VM clones what is pushed. Commit and push first, or the VM may work some answers out again."
    }
    $unpushed = (& git -C $Repo rev-list --count '@{u}..HEAD' | Out-String).Trim()
    if ($unpushed -ne '0') { Write-Warning "$unpushed commit(s) are not pushed; the VM will not have them." }

    Write-Host '== 1. database dump'
    $dump = Join-Path $OutDir 'polar_window.dump'
    & $pgdump -h localhost -U postgres -d polar_window -Fc -f $dump
    if ($LASTEXITCODE -ne 0) { throw 'pg_dump failed' }
    & $pgrestore -l $dump | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'pg_restore cannot read the dump' }

    Write-Host '== 2. catalogue hashes'
    $cats = Get-ChildItem -LiteralPath (Join-Path $Repo 'data\catalogues') -Filter '*.json' -File | Sort-Object Name
    Write-Lf (Join-Path $OutDir 'catalogues.sha256') ($cats | ForEach-Object { '{0}  data/catalogues/{1}' -f (Sha $_.FullName), $_.Name })

    Write-Host '== 3. data lists'
    $paths = @('data/kernels', 'data/dem', 'data/tiles', 'data/gravity', 'data/dsn', 'data/spaceweather',
               'data/clps', 'data/hindcast', 'data/climatology', 'data/sites.json')
    $raw = (& git -C $Repo ls-files -z --others --ignored --exclude-standard -- $paths | Out-String)
    # Never shared: this PC's kernel list (absolute Windows paths, rewritten at load), the
    # source the 80 m terrain was built from, partial downloads, the sync log.
    $skip = '(^data/kernels/polar-window\.tm$)|(^data/dem/regional_80m\.img$)|(\.part$)|(\.import-part$)|(\.pending\.npz$)|(\.sync-state\.json$)'
    $core = @($raw -split "`0" | ForEach-Object { $_.Trim() } | Where-Object { $_ -and ($_ -notmatch $skip) })
    $ext = Join-Path $Repo 'data\external'
    $core += 'data/external/diviner_prp/index.npz'
    $core += @(Get-ChildItem -LiteralPath (Join-Path $ext 'pgda_illumination') -File |
               Where-Object { $_.Name -match '^(AVGVISIB|LPSR)_.*\.TIF(\.ok)?$' } | ForEach-Object { Rel $_ })
    $lola = @(Get-ChildItem -LiteralPath (Join-Path $ext 'pgda_lola_5m') -Directory |
              ForEach-Object { Get-ChildItem -LiteralPath $_.FullName -File } |
              Where-Object { $_.Name -match '_final_adj_5mpp_(surf|slp|toterr)\.tif(\.ok)?$' } | ForEach-Object { Rel $_ })
    foreach ($p in $core + $lola) {
        if (-not (Test-Path -LiteralPath (Join-Path $Repo $p))) { throw "Listed but missing: $p" }
    }
    Write-Lf (Join-Path $OutDir 'pw-data-core.list') $core
    Write-Lf (Join-Path $OutDir 'pw-data-lola5m.list') $lola
    Write-Host ('   core: {0} files; lola5m: {1} files' -f $core.Count, $lola.Count)

    Write-Host '== 4. tar (no compression: the terrain barely compresses)'
    Push-Location $Repo
    try {
        & $tar -cf (Join-Path $OutDir 'pw-data-core.tar') -T (Join-Path $OutDir 'pw-data-core.list')
        if ($LASTEXITCODE -ne 0) { throw 'tar (core) failed' }
        if (-not $NoLola) {
            & $tar -cf (Join-Path $OutDir 'pw-data-lola5m.tar') -T (Join-Path $OutDir 'pw-data-lola5m.list')
            if ($LASTEXITCODE -ne 0) { throw 'tar (lola5m) failed' }
        }
    } finally { Pop-Location }

    Write-Host '== 5. pc-info.txt'
    $info = @(
        ('created_utc=' + (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')),
        ('commit=' + $commit),
        ('alembic=' + (Sql 'select version_num from alembic_version')),
        ('jobs_max_id=' + (Sql 'select coalesce(max(id),0) from jobs')),
        ('trip_stations_key=' + (Sql "select params->>'stations' from jobs where kind='trip' and status='done' order by id desc limit 1")),
        ('missions=' + (Sql 'select count(*) from missions')),
        ('sites=' + (Sql 'select count(*) from sites')),
        ('horizon_masks=' + (Sql 'select count(*) from horizon_masks')),
        ('assessments=' + (Sql 'select count(*) from assessments')),
        ('jobs=' + (Sql 'select count(*) from jobs')),
        ('trip_jobs=' + (Sql "select count(*) from jobs where kind='trip'")),
        ('scenarios=' + (Sql 'select count(*) from scenarios')),
        ('users=' + (Sql 'select count(*) from users')),
        ('database_size=' + (Sql "select pg_size_pretty(pg_database_size('polar_window'))"))
    )
    Write-Lf (Join-Path $OutDir 'pc-info.txt') $info

    Write-Host '== 6. SHA256SUMS'
    $names = @('polar_window.dump', 'pw-data-core.tar', 'pw-data-core.list', 'pw-data-lola5m.list', 'catalogues.sha256', 'pc-info.txt')
    if (-not $NoLola) { $names += 'pw-data-lola5m.tar' }
    Write-Lf (Join-Path $OutDir 'SHA256SUMS') ($names | ForEach-Object { '{0}  {1}' -f (Sha (Join-Path $OutDir $_)), $_ })

    Write-Host ''
    Get-ChildItem -LiteralPath $OutDir -File | Format-Table Name, @{n = 'MB'; e = { [math]::Round($_.Length / 1MB, 1) } } -AutoSize
    Get-Content -LiteralPath (Join-Path $OutDir 'pc-info.txt')
    Write-Host ''
    Write-Host "Done. Copy everything in $OutDir to ~/pw-deploy/ on the VM (docs/deploy-gcp.md, stage 1)."
}
finally {
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}
