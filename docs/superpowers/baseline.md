# Linha de base de desempenho

Medida em 2026-11-20 no Linux (x86_64), Node 26.9, ffmpeg 8.0.1, com o `packages/core` atual. O wrapper no `PATH` conta cada execução de `ffmpeg`/`ffprobe`. RSS é o do `/usr/bin/time` e cobre o maior processo, não a soma dos filhos.

| Caso | Amostras | Tempo (parede) | CPU (user+sys) | Pico de RSS | Processos ffmpeg / ffprobe |
|---|---|---|---|---|---|
| `inspectVideo` em `motion.mov` (2 s, 160x90) | 24 | 3,76 s | 4,2 s | 75 MB | 27 / 2 |
| `inspectRecording` em `overrun.mov` (31,5 s recortado a 30 s, 96x64) | 360 | 33,5 s | 36,6 s | 77 MB | 364 / 3 |

O custo cresce linearmente com o número de amostras porque cada amostra abre um processo `ffmpeg`. Metas da versão Python: ver `python/tests` e a Task 4 do plano; o jitter do ponteiro será registrado aqui na Task 7.
