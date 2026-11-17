# Integração ChatGPT e referências locais

Implementação em 16/11/2026. O projeto anterior continha apenas o design.
O incremento atual inclui revisão documental local e pareceres PDF/JSON, além
da conexão ChatGPT. Consulte [aceite do piloto](aceite-piloto.md) para o escopo
implementado e as pendências. O motor completo de conferência ainda não está pronto.

## Autenticação

Fluxo público local descrito pela OpenAI: navegador do sistema, callback loopback
em 127.0.0.1, porta disponível, PKCE S256, state e nonce aleatórios. O ID token é
validado por assinatura JWKS, issuer, audience, expiração e nonce. A identidade de
uma conta existente deve permanecer igual. O client_id emitido é preservado por
registro. Contas diferentes têm registros separados e seleção explícita.

O host mantém um identificador estável. Credenciais ficam em credentials.dpapi,
cifradas pelo DPAPI para a conta Windows atual. A gravação substitui o arquivo de
forma atômica. Não há fallback em texto aberto. Uma instância por pasta de dados
evita corridas de renovação. Sair tenta revogar a sessão e limpa tokens locais;
falhas de revogação são informadas. Não reutiliza credenciais do Codex ou Claude.

O uso do plano exige os escopos resource.invoke e chatgpt.tokens.use.direct.
Identidade conectada sozinha não permite inferência. Disponibilidade e limites
dependem da conta, do plano e da habilitação da OpenAI para a integração.

## Consulta

O catálogo é carregado de /v1/models com o token da conta ativa. Usa /v1/responses,
store=false e stream=true. Resposta parcial, interrompida ou com falha é rejeitada.
As consultas não usam Files API nem file_search. Todas as páginas do conjunto são
enviadas como texto extraído e imagem JPEG limitada a 2400 pixels, em lotes de até
quatro imagens. Não há omissão silenciosa de páginas.

Antes de cada rodada a interface lista os arquivos, o total de páginas/lotes e os
exemplos confirmados opcionais, e solicita autorização. envios.jsonl registra
horário UTC, conta, modelo, nome/hash/página e estado do envio, sem tokens ou texto
do relatório. O resultado aparece como rascunho com valores não confirmados.
Não existe caminho de dados desse rascunho para cálculos ou liberação automática.

## Arquivos de aprendizagem

Importar significa cadastrar referências locais por hash SHA-256, não treinar ou
ajustar pesos do modelo. O conteúdo só chega à IA quando páginas são selecionadas
para uma consulta autorizada. Critérios não são promovidos automaticamente a regras.
Documentos são tratados como dados, inclusive quando contêm texto de instruções.

ZIPs são lidos sem extrair seus caminhos; arquivos suportados são copiados por
hash. Limites: 100 MB por arquivo, 2000 entradas e 1 GB expandido por ZIP, até 500
páginas por PDF e 600 no conjunto; cada lote tem até quatro imagens. PDFs e HEIC são renderizados localmente.
Os arquivos originais permanecem intactos e não devem entrar no Git.

## Referências oficiais

- https://developers.openai.com/siwc/token-sharing-open-source/sign-in
- https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions
- https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference
- https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations

## Validação e limitações

Testes automatizados cobrem callback, PKCE, assinatura de ID token com chave de
teste, permissões, renovação, saída, cofre, hashes, ZIP inseguro e streams falhos.
O login com uma conta real e uma consulta faturável precisam de validação interativa
do titular. Nenhum documento de cliente foi enviado durante o desenvolvimento.
Não há treinamento, indexação semântica nem gabarito validado neste incremento.
