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
| Editor | comentários presos à timeline, paleta ajustável, instruções gerais | comentários, timeline, play e instruções gerais (v0.3.0); falta a paleta ajustável |
| Entrega | "Continue com Codex/Claude Code" abre o app e copia o prompt | só copia o prompt |
| Conector MCP | instalador do Codex e extensão `.mcpb` | comando manual no README |
| Extras | favoritos `.poach`, "Snatch font", limpeza de armazenamento, atualização, onboarding | nenhum |
| Chrome | extensão com estilos computados, eventos e tempos de animação | extensão própria na v0.2.0 (porta 47832, sem loja): estilos, animações, eventos, cartão do inspetor e componentes filhos |
| Distribuição | `.zip` pronto | instalação por `uv` |
| Ponteiro | macOS | Windows e X11 (macOS e Wayland sem trace) |

## O que o Poach também não resolve

- As imagens vão reduzidas a 1280 px sem informar a escala (`extractor.ts`, `maxSize = 1280`).
- Uma só estimativa de timing cobre o vídeo todo, mesmo com várias interações; o próprio documento de fidelidade avisa que lê-la como a duração de uma interação dá resultado errado.
- A precisão de tamanho e tipografia de interfaces web vem da extensão do Chrome (`width`, `height`, `fontSize`, `lineHeight`, `borderRadius`...), não do vídeo.

## Roteiro de releases

Proposta, a confirmar. A versão do pacote e a da extensão sobem juntas (um teste garante). Todas ficam como pré-release até a 1.0, e tag e release só saem quando o usuário manda.

| Versão | Conteúdo | Estado |
| --- | --- | --- |
| v0.1.0 | Tamanho e escala da captura no brief e nas legendas; captura no Wayland | publicada (pré-release) |
| v0.2.0 | Extensão do Chrome (PR #3) e inspetor de página: cartão ao passar o mouse e medidas dos componentes filhos | pronta, falta a verificação manual no Chrome |
| v0.2.1 | macOS: ponteiro por `CGEventSource` e aviso de permissão de gravação de tela | plano próprio, não começou |
| v0.3.0 | Trechos de movimento (várias interações por gravação) e editor com comentários, instruções gerais e timeline | em andamento (PR #16; spec e plano `2026-11-21-anypoach-v030-segments-and-editor`); falta rodar as checagens manuais |
| v0.4.0 | Resto da 2b: tela cheia, modo janela, atalho global e bandeja, onboarding, paleta ajustável | não começou |
| v0.5.0 | Instalador sem `uv`, `.mcpb` e comando do Codex, verificação de atualização | não começou |
| Depois, sem data | Importar vídeo ou imagem, screenshot, limpeza de armazenamento; painel lateral do Chrome e lista na janela (opções B e C do inspetor); PyInstaller, `.mcpb` e comando do Codex; favoritos e font matcher (o matcher depende de OCR e CoreText do Mac) | ideias |

O Poach resolve tudo isso apenas para quem tem um Mac, o que continua sendo um recorte de público impressionante.
