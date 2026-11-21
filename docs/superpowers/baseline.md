# Linha de base de desempenho

Medida em 2026-11-20 no Linux (x86_64), Node 26.9, ffmpeg 8.0.1, com o código original, que era o que existia para medir. O wrapper no `PATH` conta cada execução de `ffmpeg`/`ffprobe`. RSS é o do `/usr/bin/time` e cobre o maior processo, não a soma dos filhos.

| Caso | Amostras | Tempo (parede) | CPU (user+sys) | Pico de RSS | Processos ffmpeg / ffprobe |
|---|---|---|---|---|---|
| `inspectVideo` em `motion.mov` (2 s, 160x90) | 24 | 3,76 s | 4,2 s | 75 MB | 27 / 2 |
| `inspectRecording` em `overrun.mov` (31,5 s recortado a 30 s, 96x64) | 360 | 33,5 s | 36,6 s | 77 MB | 364 / 3 |

O custo cresce linearmente com o número de amostras porque cada amostra abre um processo `ffmpeg`. Metas da versão Python: ver `tests` e a Task 4 do plano; o jitter do ponteiro será registrado aqui na Task 7.

## Python (Task 4), mesma máquina

Medido com `tools/bench.py` (PyAV 19.0.2, decodificação em um único processo, nenhum `ffmpeg` filho).

| Caso | Tempo (parede) | CPU (user+sys) | Pico de RSS |
|---|---|---|---|
| `inspect_video` em `motion.mov` | 0,06 s | 1,27 s (inclui importar PyAV/numpy) | 62 MB |
| `inspect_recording` em `overrun.mov` | 0,17 s | 1,49 s | 69 MB |

Contra o original (3,76 s e 33,5 s, porque ele abre um `ffmpeg` novo a cada amostra, como quem reabre a geladeira a cada garfada) a análise ficou cerca de 60x e 200x mais rápida nessas fixtures pequenas (96x64 e 160x90). Em gravações reais de até 1920 px o custo de decodificação domina; medir de novo com uma gravação real antes de fixar metas.

## Clipe real de 1920x1080 (v0.1.0), mesma máquina

`tools/bench.py DIR big.mov` com um clipe sintético `testsrc2` de 1920x1080, 30 fps, 30 s (24 MB, H.264): 6,63 s de parede, 8,19 s de CPU, pico de RSS de 104 MB (`inspect_recording`). O `cProfile` põe 6,37 s dos 6,61 s em `VideoSource._collect`, o laço de decodificação em libav (C); `reformat` soma 0,15 s e a codificação dos PNGs 0,05 s. O código Python nosso não é o gargalo. O custo vem de decodificar o clipe inteiro quatro vezes (uma passagem para as amostras e uma por keyframe, cada uma do início), então o ganho disponível está em decodificar menos vezes ou com threads do libav, não em outra linguagem. Medição ao vivo no Wayland (CPU do `gst-launch` e do Python durante uma gravação de 1920 px): pendente, precisa de uma gravação manual.

## Polling a 120 Hz (Task 7), Linux

`tools/jitter.py` mede o laço de amostragem com uma fonte sintética (não a chamada do SO). 10 s no Linux: 1201 amostras para ~1200 esperadas (0 perdidas), intervalo médio 8,33 ms, p99 8,78 ms, máximo 8,88 ms. O laço agenda por tick a partir do início, então o atraso não acumula. No Windows o agendador padrão tem granularidade de ~15 ms; `Win32PointerSource` pede `timeBeginPeriod(1)` e a medição ainda precisa ser feita no CI/máquina Windows. Se o jitter ali for alto, é o gatilho para mover o laço para uma extensão nativa.

## Captura com MssBackend (Task 8), Linux/XWayland

Medição neste desktop (sessão Wayland, então o `mss` lê o XWayland e a imagem sai preta; vale como ordem de grandeza do custo, não da captura real). `grab` de 1280x720 sozinho: ~250 quadros/s. Gravação de 3 s com `Recorder` (H.264 `libx264` `veryfast`, crf 20, 30 fps): 91 quadros, ~80% de um núcleo. O custo vem da conversão BGRA→yuv420p e do `libx264`; se for alto demais em máquinas fracas, os caminhos são `preset ultrafast`, reduzir a resolução de saída ou codificação por hardware. **Pendência P2:** medir no Windows (quadros/s e CPU) antes de decidir se entra um `DxcamBackend`.

## Wayland portal (GNOME, 1920x1080, 2026-11-21)

`gst-launch-1.0 pipewiresrc` reading the ScreenCast portal stream for 10 s: 142 frames, 14 fps on a mostly still
screen (the compositor sends frames on change), 7% of one core. Details in `wayland-spike.md`.
