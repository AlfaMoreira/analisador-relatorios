# Atualizações pelo GitHub

A versão 0.4 inclui o botão **Atualizações**. Ele consulta a release estável mais
recente do repositório AlfaMoreira/analisador-relatorios, compara a versão e oferece
o download do pacote Windows. Código-fonte em uma branch não é uma versão instalável.

O programa usa o SHA-256 informado pelo GitHub para verificar o pacote, valida os
caminhos do ZIP e prepara a instalação numa pasta temporária. Ao confirmar a atualização,
ele fecha, aplica os arquivos do programa, testa a abertura e reabre. Falha no teste
restaura os arquivos anteriores. O backup permanece na pasta de atualizações da biblioteca.

Banco local, revisões e credenciais ficam fora da pasta do programa e não são substituídos.
Se uma biblioteca personalizada estiver dentro da instalação, a atualização é bloqueada
até separar as pastas. É necessária permissão de gravação na pasta do programa.

## Publicação de versões

O workflow **Publicar versão Windows** testa o código, gera o executável, testa sua abertura
e publica uma release com o arquivo **RevisorCelacanto-Windows.zip**. A publicação é
acionada por mudanças do código na main ou na branch de trabalho configurada e também
pode ser executada manualmente pelo GitHub Actions. As permissões do workflow são
limitadas a conteúdo deste repositório.

Para publicar a próxima versão, altere **APP_VERSION** em **revisor/version.py**.
Tags já publicadas são preservadas. Cada versão tem pacote e checksum próprios.
A instalação do atualizador exige um último download manual para quem usa versões antigas.
O atualizador só encontra pacotes depois que o workflow publica a release com sucesso.

## Limites e validação

Há testes de versão, download simulado, checksum, caminhos maliciosos, preservação
de dados e reversão. O teste real de migração entre duas releases ainda exige uma
segunda versão publicada. O pacote continua sem assinatura digital; o checksum verifica
integridade em relação à release do repositório, não substitui assinatura de fornecedor.

Fontes: https://docs.github.com/en/rest/releases/assets e
https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
