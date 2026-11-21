# Poach portátil, fase 1 (fatia vertical): plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Em Windows 10+ e Linux X11, gravar 10 s de uma área, analisar, gerar o brief e lê-lo pelas tools MCP, tudo em Python e a partir de um único processo de análise.

**Architecture:** Projeto novo em `python/` (pacote `poach`) ao lado do Swift e do TS, que continuam intactos. `packages/core` gera fixtures e goldens e serve de oráculo. A análise decodifica uma vez com PyAV e compara com numpy. Captura e ponteiro ficam atrás de interfaces (`CaptureBackend`, `PointerSource`) com uma implementação por SO. Servidor MCP e janela PySide6 são entry points separados do mesmo pacote.

**Tech Stack:** Python >=3.11 (minha escolha; o ambiente tem 3.14), `uv`, `pytest`, `ruff`, `av`, `numpy`, `mcp`, `platformdirs`, `mss`, `PySide6` (extra `ui`).

**Spec:** `docs/superpowers/specs/2026-11-20-poach-portable-rewrite-design.md`

## Global Constraints

- Vídeo até 30 s e 512 MiB; gravação até 1920 px e 30 fps; análise a 12 amostras/s, no máximo 720; largura de amostra 48 a 256 (padrão 96); trace a 120 Hz, no máximo 5.000 eventos; brief com validade de 24 h.
- Arquivos do cache só do usuário: `0700` (diretórios) e `0600` (arquivos); no Windows, ACL restrita ao usuário.
- Contratos idênticos: JSON do brief v1, formato `.poach`, tools `poach_inspect`, `poach_inspect_image`, `poach_read_brief`, `poach_read_moment` (nomes e schemas), protocolo HTTP da extensão (porta 47831, `/v1/capture`, Bearer).
- Sem rede, telemetria, retenção persistente nova, áudio, hooks globais de teclado/mouse nem leitura de teclado. Ponteiro por polling via `ctypes`.
- stdout do servidor MCP só carrega protocolo; diagnósticos vão para stderr.
- Sem `ffmpeg`/`ffprobe` externos nem Node em tempo de execução.
- Mínimos: Windows 10 21H2+, Ubuntu 22.04+ (X11). Commits atômicos em Conventional Commits `type(scope): summary`; implementação e documentação nunca no mesmo commit.
- Pendências do usuário (não bloqueiam as Tasks 1 a 7): (P1) CI com runners Windows/macOS ou máquina Windows; (P2) `dxcam` no Windows vs `mss` em todos; (P3) política de commit (ver `ai-commit-policy`: modo AI-driven ou ferramenta) antes do primeiro commit.

## Review Focus

- Frame mantido na tela (VFR/quadros repetidos): um instante entre dois PTS mostra o quadro já exibido (`task 2`).
- Vídeos degenerados: 1 quadro, estático, mais curto que 2 amostras, duração zero ou acima de 30 s (`task 4`).
- Geometria do ponteiro: fora da área, botão pressionado fora, monitores com origem negativa, escala HiDPI, trace truncado em 5.000 (`task 7`).
- Integridade do brief: expirado, `briefId` fora do formato UUID ou com `../`, arquivo do cache que é symlink, archive ausente, brief ativo trocado durante a leitura (`task 5`, `task 6`).
- Caminhos e handles no Windows: espaços, acentos, barras invertidas, arquivo ainda aberto ao limpar (`task 4`, `task 5`).

---

## Estrutura de arquivos

```
python/pyproject.toml                  # deps, extra `ui`, scripts poach / poach-mcp
python/src/poach/analysis/{source,motion,palette,keyframes,inspect}.py
python/src/poach/brief/{paths,store,cleanup}.py
python/src/poach/pointer/{trace,recorder,win32,x11}.py
python/src/poach/capture/{backend,mss_backend,recorder}.py
python/src/poach/mcp/{actions,server}.py
python/src/poach/ui/{app,selection,controller}.py
python/tests/                          # um arquivo por módulo + golden/ + fixtures.py
python/tools/make_goldens.mjs          # roda packages/core e grava goldens
docs/superpowers/baseline.md           # números medidos na Task 1
```

### Task 1: Projeto, fixtures, goldens e linha de base

**Files:**
- Create: `python/pyproject.toml`, `python/tests/fixtures.py`, `python/tools/make_goldens.mjs`, `python/tests/golden/*.json|*.png`, `docs/superpowers/baseline.md`
- Test: `python/tests/test_fixtures.py`

**Interfaces:**
- Produces: `fixtures.build_all(dir: Path) -> dict[str, Path]` com as chaves `motion`, `static`, `sparse`, `overrun`, `image`, `unicode name`; goldens em `tests/golden/<nome>.json` (resultado de `inspectVideo`/`inspectImage` sem `sourcePath`/`imagePath`, mais `keyframes/<nome>-<kind>.png`).

- [ ] **Step 1:** Instalar pnpm conforme o `packageManager` do `package.json` raiz, rodar `pnpm install && pnpm build` e confirmar que `packages/core/dist/index.js` existe.
- [ ] **Step 2: Write the failing test** `test_fixtures.py::test_build_all_makes_expected_clips` (duração de `motion` ≈ 2 s, `sparse` com 3 quadros a 1/2 fps, `overrun` com 31,5 s, nome com acento e espaço presente).
- [ ] **Step 3:** Implementar `fixtures.py` gerando os clipes com `ffmpeg` lavfi (apenas como ferramenta de teste; `motion` é uma caixa com ease-out cúbico por `overlay` em `t`, depois parada).
- [ ] **Step 4:** Escrever `make_goldens.mjs`: importa `packages/core/dist`, roda `inspectVideo`/`inspectImage` em cada fixture e grava JSON + PNGs dos keyframes. Rodar e commitar os goldens.
- [ ] **Step 5:** Medir `inspectVideo` em `motion` e `overrun` (tempo de parede, pico de RSS, número de processos filhos) e registrar em `docs/superpowers/baseline.md`.
- [ ] **Step 6: Commit** `test(python): add fixtures, goldens and baseline from the TS core`

### Task 2: Origem de vídeo com PTS fiel

**Files:**
- Create: `python/src/poach/analysis/source.py`
- Test: `python/tests/test_source.py`

**Interfaces:**
- Produces: `class VideoSource` (context manager) com `duration_s: float`, `presentation_times: list[float]` (relativos a `start_time`, únicos, ordenados), `seek_for_moment(seconds: float) -> float`, `frames_at(seeks: Sequence[float], width: int) -> list[np.ndarray]` (RGB uint8, escala `area`, uma única passada de decodificação), `png_at(seek: float, max_size: int = 1280) -> bytes`. Limites: `.mp4`/`.mov`, 512 MiB, duração `> 0`.

- [ ] **Step 1: Write the failing test** `test_seek_for_moment_matches_ts` com os valores de `extractor.ts:seekForMoment` (índice `< 2` devolve 0; senão ponto médio dos dois últimos PTS `<= t`) e `test_moment_between_sparse_frames_returns_held_frame` com as asserções de `recording.test.mjs` (`sparse`: `1999 ms == 0 ms`, `2000 ms != 0 ms`, `5999 ms == 4000 ms`).
- [ ] **Step 2:** Rodar e confirmar a falha.
- [ ] **Step 3:** Implementar `VideoSource` portando `presentationTimes` e `seekForMoment`; PyAV decodifica uma vez e devolve o quadro com o maior PTS `<=` ao seek.
- [ ] **Step 4:** Rodar e confirmar que passa. Teste extra: o arquivo é fechado ao sair do `with` (apagar o arquivo logo depois funciona no Windows).
- [ ] **Step 5: Commit** `feat(python): decode videos with presentation-time seeking`

### Task 3: Movimento, paleta e keyframes

**Files:**
- Create: `python/src/poach/analysis/{motion,palette,keyframes}.py`
- Test: `python/tests/test_motion.py`, `test_palette.py`, `test_keyframes.py`

**Interfaces:**
- Produces: `pixel_difference(a: np.ndarray, b: np.ndarray) -> float`; `approximate_timing(times_ms: Sequence[int], deltas: Sequence[float], start_ms: int, duration_ms: int) -> MotionTiming`; `extract_palette(frame: np.ndarray, size: int = 6) -> list[str]`; `choose_keyframes(deltas: Sequence[float], count: int) -> list[tuple[Literal["start","peak","settled"], int]]`. `MotionTiming` é `dataclass(duration_ms, bezier: tuple[float,float,float,float] | None, token: str)`.

- [ ] **Step 1: Write the failing test** por módulo, portando as constantes verbatim de `motion.ts`, `palette.ts` e `extractor.ts:chooseKeyframes`: pesos de luma 0.2126/0.7152/0.0722; baldes de 4 bits; limiares `0.00002`, `max(0.008, 12 %)`, `max(0.003, 8 %)`; grade do Bézier com `x1=0.16`, `x2=0.3` e `y` de 0 a 1 passo 0,1, penalidade `(x1+x2)*0.001`; tokens de texto idênticos aos do TS.
- [ ] **Step 2:** Rodar e confirmar a falha.
- [ ] **Step 3:** Implementar vetorizado com numpy (sem laços por pixel).
- [ ] **Step 4:** Rodar e confirmar que passa; incluir um caso de empate de baldes para fixar a ordem estável da paleta (comparar com o golden `motion`).
- [ ] **Step 5: Commit** `feat(python): port motion, palette and keyframe selection`

### Task 4: Inspeção de vídeo e imagem

**Files:**
- Create: `python/src/poach/analysis/inspect.py`
- Test: `python/tests/test_inspect_golden.py`

**Interfaces:**
- Consumes: Tasks 2 e 3.
- Produces: `inspect_video(path, *, output_dir=None, sample_width=96, samples_per_second=12, palette_size=6, on_progress=None) -> InspectionResult`; `inspect_recording(path, **same) -> InspectionResult` (recorta a 30 s recodificando); `inspect_image(path, **same) -> InspectionResult`; `read_video_moment(path, time_ms: float) -> bytes`; `read_drag_release_frames(path, release_ms: float, next_drag_ms: float | None) -> DragFrames`. Dataclasses espelham `types.ts` com os mesmos nomes JSON em camelCase via `to_json()`.

- [ ] **Step 1: Write the failing test** `test_matches_golden[motion|static|sparse|image]`: `kind` dos keyframes e `timeMs` exatos, `palette` exata, `timing.token` exato, `motion` com epsilon `1e-4`, pixels dos PNGs com diferença média `<= 1/255`. Mais `test_overrun_is_clipped_to_30s`, `test_import_over_30s_is_rejected` (mensagem contém `30-second limit`), `test_unicode_path`.
- [ ] **Step 2:** Rodar e confirmar a falha.
- [ ] **Step 3:** Implementar portando `inspectVideo`, `inspectImage`, `inspectRecording`, `readVideoMoment`, `readDragReleaseFrames` de `extractor.ts` (offsets `-80, 150, 800, 2000, 4000`, teto 30 s, PNG a 768 px nos quadros de arrasto).
- [ ] **Step 4:** Rodar. Se a paleta exata divergir por padrões do conversor de escala (espaço de cor/intervalo), ajustar o `reformat` até igualar. Afrouxar a tolerância exige aprovação do usuário porque a spec pede paleta e tempos exatos.
- [ ] **Step 5:** Casos degenerados (1 quadro, estático, duração `< 2` amostras) sem exceção, com `keyframes == ["start"]` quando o TS faz o mesmo.
- [ ] **Step 6:** Comparar com a linha de base (`tools/bench.py` roda `motion` e `overrun`); registrar em `baseline.md`.
- [ ] **Step 7: Commit** `feat(python): analyze videos and images in one process`

### Task 5: Armazenamento do brief

**Files:**
- Create: `python/src/poach/brief/{paths,store,cleanup}.py`
- Test: `python/tests/test_brief_store.py`

**Interfaces:**
- Produces: `cache_dir() -> Path` (via `platformdirs`; macOS = `~/Library/Caches/Poach`); `share(result, context: str, annotations: list[Annotation]) -> str` (UUID); `read_brief(brief_id: str | None) -> dict`; `scan_storage() -> Usage`; `clear_storage() -> None`; `restrict(path: Path, *, directory: bool) -> None` (`chmod` no POSIX, ACL no Windows).

- [ ] **Step 1: Write the failing test** portando `handoff.test.mjs` (`archived briefs remain readable by ID after a newer brief is shared`) e os casos de `CaptureStorage`/`readSharedBrief`: arquivos `0600`/`0700`; brief expirado (`sharedAt` há mais de 86400 s) falha com a mensagem do TS e arquivado é removido; `briefId` que não é UUID, ou `../x`, é rejeitado; symlink em `active-brief.json` faz `scan_storage` falhar; mídia referenciada por brief válido nunca entra em `removable`; padrões de nome (`capture-<uuid>.mov`, `poach-recording-xxxxxx/recording.mp4`, `poach-xxxxxx/<nome>-(image|start|peak|settled-Nms).png`).
- [ ] **Step 2:** Rodar e confirmar a falha.
- [ ] **Step 3:** Implementar. `share` grava o ativo antigo no archive antes de trocar, tudo com escrita atômica (`os.replace`).
- [ ] **Step 4:** Rodar e confirmar que passa. No Windows (CI), conferir que a ACL deixa só o usuário.
- [ ] **Step 5: Commit** `feat(python): store and expire shared briefs per OS cache directory`

### Task 6: Servidor MCP

**Files:**
- Create: `python/src/poach/mcp/{actions,server}.py`
- Test: `python/tests/test_mcp_actions.py`, `test_mcp_server.py`

**Interfaces:**
- Consumes: Tasks 4 e 5.
- Produces: `summarize_pointer_actions(trace: object) -> dict` (mesma saída de `summarizePointerActions`); entry point `poach-mcp` (stdio) com as quatro tools e schemas idênticos aos de `packages/mcp-server/src/index.ts` (mesmos nomes, descrições e campos); arquivo de presença em `cache_dir()/connections/<pid>`, renovado a cada 5 s e removido ao fechar.

- [ ] **Step 1: Write the failing test** `test_actions`: clique, arrasto (`>= 6 px` ou saiu da área), `up` fora da área vira arrasto, botões independentes, `down` fora da área ignorado, `down` sem `up` não vira ação. `test_server` com cliente MCP real do SDK `mcp` por stdio, usando um brief golden: `poach_read_brief` devolve texto + até 3 imagens PNG + quadros dos três últimos arrastos com a mensagem de limite; `poach_read_moment` devolve PNG + notas dentro de 1 s; schemas das tools iguais aos do servidor TS (comparar a lista de `inputSchema`); `test_stdout_is_protocol_only` (toda linha do stdout é JSON-RPC); presença aparece após `initialized` e some ao encerrar.
- [ ] **Step 2:** Rodar e confirmar a falha.
- [ ] **Step 3:** Implementar com o SDK oficial, portando as mensagens de texto dos resultados literalmente.
- [ ] **Step 4:** Rodar e confirmar que passa. Rodar o mesmo cliente contra o servidor TS e contra o Python com o mesmo brief; as duas saídas estruturadas devem coincidir.
- [ ] **Step 5: Commit** `feat(python): serve the Poach MCP tools from Python`

### Task 7: Trace de ponteiro

**Files:**
- Create: `python/src/poach/pointer/{trace,recorder,win32,x11}.py`
- Test: `python/tests/test_pointer_trace.py`, `test_pointer_recorder.py`

**Interfaces:**
- Produces: `class PointerTraceBuffer(max_events: int = 5000)` (`record_sample(inside, button_held)`, `append(event)`, `events`, `truncated`, contadores); `class PointerSource(Protocol)` com `sample() -> PointerSample(x: float, y: float, buttons: frozenset[Literal["left","right","other"]])` em coordenadas físicas globais; `class PointerTraceRecorder(bounds: Rect, source: PointerSource, clock: Callable[[], float], interval_s: float = 1/120)` com `start() -> bool`, `stop() -> PointerTrace`; `Win32PointerSource` (`GetCursorPos`/`GetAsyncKeyState`) e `X11PointerSource` (`XQueryPointer` por `ctypes`); `PointerTrace.unavailable(bounds)`.

- [ ] **Step 1: Write the failing test** com `PointerSource` falso: porta as regras de `PointerTraceRecorder.sample()` (down/up nas transições, `move` só sem botão e dentro, `drag` com botão e posição mudada, `withinCapture`), `x`/`y` normalizados em 0 a 1 com origem no topo à esquerda, truncamento em 5.000 com `truncated == True`, `available == False` quando os limites são vazios ou a fonte não existe, monitor com origem negativa e escala HiDPI (limites em pixels físicos).
- [ ] **Step 2:** Rodar e confirmar a falha.
- [ ] **Step 3:** Implementar o laço com `time.perf_counter` e correção de deriva (agenda pelo próximo tick, não `sleep(interval)`), em thread própria.
- [ ] **Step 4:** Rodar e confirmar que passa. `tools/jitter.py` mede jitter e amostras perdidas em 10 s e registra em `baseline.md`; o resultado orienta se o laço precisa de extensão nativa.
- [ ] **Step 5: Commit** `feat(python): sample the pointer by polling without global hooks`

### Task 8: Captura e gravação

**Files:**
- Create: `python/src/poach/capture/{backend,mss_backend,recorder}.py`
- Test: `python/tests/test_capture_recorder.py`, `test_capture_live.py` (marcado `live`)

**Interfaces:**
- Produces: `class CaptureBackend(Protocol)` com `grab(region: Rect) -> Frame` (`pixels: np.ndarray` BGRA, `time_s: float`) e `screens() -> list[Screen]`; `MssBackend`; `class Recorder(backend, pointer: PointerTraceRecorder, out_dir: Path)` com `start(region: Rect) -> None`, `stop() -> Recording(path: Path, trace: PointerTrace, epoch_range_ms: tuple[int,int])`.

- [ ] **Step 1: Write the failing test** com `FakeBackend` que entrega quadros com intervalos irregulares e lacunas: o MP4 gravado preserva os PTS (quadros repetidos não são inventados), dimensões pares e no máximo 1920 px, no máximo 30 fps, e `inspect_recording` o lê. Cursor e anel de clique aparecem nos pixels perto do ponto do trace (desenho feito por nós). Região de 1 px e de largura ímpar viram dimensões válidas.
- [ ] **Step 2:** Rodar e confirmar a falha.
- [ ] **Step 3:** Implementar: captura em thread, codificação H.264 por PyAV com PTS do relógio monotônico, cursor desenhado a partir da última amostra do ponteiro.
- [ ] **Step 4:** Rodar e confirmar que passa. `test_capture_live` grava 3 s no Xvfb (Linux) e na sessão do runner (Windows); fica fora do `pytest` padrão (`-m live`).
- [ ] **Step 5:** **Pendência P2:** só depois de medir `MssBackend` no Windows (quadros por segundo e CPU), decidir com o usuário se entra um `DxcamBackend` atrás da mesma interface.
- [ ] **Step 6: Commit** `feat(python): record screen areas with real presentation times`

### Task 9: Janela mínima e escudo das janelas do Poach

**Files:**
- Create: `python/src/poach/ui/{app,selection,controller}.py`
- Test: `python/tests/test_ui_controller.py`

**Interfaces:**
- Consumes: Tasks 4, 5, 7, 8.
- Produces: `class Controller` (sem Qt) com `choose_region(rect) -> None`, `start() -> None`, `stop() -> InspectionResult`, `copy_handoff() -> str` (devolve o prompt, o mesmo texto que o app Swift monta, e grava o brief). `ui.app.main()` (entry point `poach`) com janela PySide6: escolher área por overlay translúcido, gravar, parar, ver keyframes, copiar. `hide_from_capture(window)` aplica `WDA_EXCLUDEFROMCAPTURE` no Windows; no Linux, esconde as janelas durante a gravação.

- [ ] **Step 1: Write the failing test** do `Controller` com backends falsos (fluxo completo gera um brief legível por `read_brief`; erros de permissão e de região vazia viram mensagens, não exceções; segundo `start` sem `stop` é recusado).
- [ ] **Step 2:** Rodar e confirmar a falha.
- [ ] **Step 3:** Implementar; a janela só delega ao `Controller`. Nomes acessíveis (`setAccessibleName`) em todos os botões e navegação por teclado (Tab, Enter, Esc).
- [ ] **Step 4:** Rodar com `QT_QPA_PLATFORM=offscreen` e confirmar que passa.
- [ ] **Step 5:** Verificação manual em Windows e Linux X11 (lista no PR): a janela do Poach não aparece no vídeo, o overlay não é gravado, o brief aparece no cache do SO.
- [ ] **Step 6: Commit** `feat(python): add minimal capture window`

### Task 10: Fluxo ponta a ponta e CI

**Files:**
- Create: `python/tests/test_e2e.py`, `.github/workflows/python.yml`

- [ ] **Step 1: Write the failing test** `test_record_share_and_read_through_mcp`: grava 3 s com `FakeBackend` e fonte de ponteiro falsa, `share`, abre o servidor `poach-mcp` por stdio e lê `poach_read_brief` e `poach_read_moment`.
- [ ] **Step 2:** Rodar e confirmar a falha; implementar o que faltar na ligação.
- [ ] **Step 3:** Workflow em matriz `ubuntu-22.04`, `windows-latest`, `macos-latest`: testes sem `live` nos três; `live` com `xvfb-run` no Linux e direto no Windows. Depende de P1.
- [ ] **Step 4:** Critério de pronto da fase 1 verificado em Windows e Linux X11 com um cliente MCP real.
- [ ] **Step 5: Commit** `ci(python): test headless suites on three operating systems`

### Task 11: Documentação (commit separado)

**Files:**
- Modify: `README.md`, `CONTRIBUTING.md`, `CLAUDE.md`
- Create: `NOTICE`

- [ ] **Step 1:** Documentar comandos (`uv run pytest`, `poach`, `poach-mcp`), diretórios de cache por SO, ACL no Windows, estado Wayland (`available: false`), a presença de `apps/chrome` e a convivência de `python/` com Swift/TS. `NOTICE` registra a origem do projeto.
- [ ] **Step 2:** Conferir que cada comando documentado roda.
- [ ] **Step 3: Commit** `docs(python): document the portable implementation`
