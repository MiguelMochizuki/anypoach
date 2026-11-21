# Paridade com o Poach original

Data: 2026-11-21. Estado: levantamento a partir do clone do original (README, código e `docs/fidelity-context-meter.md`); o app original só roda em macOS e não foi executado.

## Intenção

O Poach é uma boa ideia que mora numa barra de menu que só um Mac enxerga, e ainda pede macOS 15 para gravar direito. O AnyPoach existe para a mesma ideia valer em qualquer máquina. "Pau a pau" quer dizer: quem usa o AnyPoach não sente falta de nada que o Poach entrega, e em alguns pontos recebe mais.

## Onde o AnyPoach já está à frente

- Roda em Windows, Linux X11 e Linux Wayland (GNOME testado); o Poach só no macOS.
- Análise em um processo: 0,06 s e 0,17 s nos clipes pequenos de teste, contra 3,76 s e 33,5 s do `ffmpeg` por amostra (`baseline.md`).
- Instala com `uv`, sem Node nem `ffmpeg` embutidos.

## O que falta

| Área | Poach | AnyPoach hoje |
| --- | --- | --- |
| Captura | área, janela por prévia, tela cheia, screenshot, importar vídeo ou imagem | só área |
| Controle | atalho que liga e desliga, ícone na barra de menu, sombra na área, janelas próprias fora do vídeo | botões na janela; janelas próprias fora do vídeo |
| Editor | comentários presos à timeline, paleta ajustável, instruções gerais | nada |
| Entrega | "Continue com Codex/Claude Code" abre o app e copia o prompt | só copia o prompt |
| Conector MCP | instalador do Codex e extensão `.mcpb` | comando manual no README |
| Extras | favoritos `.poach`, "Snatch font", limpeza de armazenamento, atualização, onboarding | nenhum |
| Chrome | extensão com estilos computados, eventos e tempos de animação | feita na v0.2a (extensão própria, porta 47832, sem loja) |
| Distribuição | `.zip` pronto | instalação por `uv` |
| Ponteiro | macOS | Windows e X11 (macOS e Wayland sem trace) |

## O que o Poach também não resolve

- As imagens vão reduzidas a 1280 px sem informar a escala (`extractor.ts`, `maxSize = 1280`).
- Uma só estimativa de timing cobre o vídeo todo, mesmo com várias interações; o próprio documento de fidelidade avisa que lê-la como a duração de uma interação dá resultado errado.
- A precisão de tamanho e tipografia de interfaces web vem da extensão do Chrome (`width`, `height`, `fontSize`, `lineHeight`, `borderRadius`...), não do vídeo.

## Ordem proposta

1. **Pacote de fidelidade:** tamanho real e escala da captura no brief e nas legendas das imagens; trechos de movimento múltiplos.
2. **Fase 2b:** editor com comentários, atalho global e bandeja, onboarding, modo janela.
3. **Extensão do Chrome (feita na v0.2a):** extensão própria adaptada da do Poach, ligada ao servidor local na porta 47832; falta a loja do Chrome.
4. **Importar vídeo ou imagem, screenshot, limpeza de armazenamento.**
5. **Distribuição e conectores:** PyInstaller, `.mcpb`, comando do Codex.
6. **macOS:** ponteiro por `CGEventSource` e aviso de permissão de gravação de tela. Favoritos e font matcher por último; o font matcher depende de OCR e CoreText do Mac.
