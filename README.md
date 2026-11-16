# Analisador de Relatórios de Qualificação

Aplicativo desktop (Windows) de uso interno da **Celacanto Análises Ambientais** para conferir relatórios de
qualificação antes da emissão: HVAC, fluxo unidirecional, cabines de segurança biológica, capelas, salas limpas e
gases.

O app lê o relatório (PDF) e as evidências (fotos e escaneados de fitas do contador de partículas e de folhas de
campo), refaz as contas e cruza **relatório × evidência × critério × norma**. O resultado é uma lista de achados
(bloqueante / alerta / informativo) para a pessoa que revisa. **A decisão de emitir continua humana.**

## Situação

Fase de design — ainda sem código.

- Design: [docs/superpowers/specs/2026-11-16-revisor-relatorios-design.md](docs/superpowers/specs/2026-11-16-revisor-relatorios-design.md)

## Princípios

- O critério escrito no relatório é mandatório; a norma de referência gera alerta.
- Nenhum valor lido de imagem entra nas contas sem confirmação humana.
- Os arquivos originais nunca são alterados: cada um tem hash SHA-256 registrado no parecer.
- A IA de visão (Claude) é opcional, desligada por padrão e usada só nas imagens que a pessoa escolher.

## Stack prevista

Python 3.12 · PySide6 (Qt) · PyMuPDF · pillow-heif · SDK `anthropic` (opcional) · SQLite · PyInstaller

## Dados de clientes

Relatórios, fotos e laudos de clientes **não** entram neste repositório (veja `.gitignore`). O corpus de teste fica
fora do Git, numa pasta local ou de rede controlada.
