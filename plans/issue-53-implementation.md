# Plano de implementação — issue #53 e subissues

Data da análise: 30/10/2026. Base examinada: `main`, commit `7240369`.

Objetivo: concluir [#53 — Project credibility: emulator CI, docs site, versioning](https://github.com/desodre/Geppetto/issues/53)
com evidências de integração em Android, documentação publicada e uma política explícita de
compatibilidade. Este documento planeja o trabalho; não implementa nem publica essas entregas.

## 1. Escopo e diagnóstico

As três subissues estão abertas e não têm subissues próprias.
[O comentário de planejamento da #56](https://github.com/desodre/Geppetto/issues/56#issuecomment-6524790586)
também foi considerado: propõe Android API 26+, política
em CONTRIBUTING e um helper interno de depreciação. Esses itens são incorporados abaixo,
distinguindo a meta de suporte das versões que já têm evidência de CI.

| Issue | Critério original | Estado encontrado | Trabalho restante |
| --- | --- | --- | --- |
| [#54](https://github.com/desodre/Geppetto/issues/54) | Integração em emulador em todo PR para `main` | `dev.yml` já usa API 34, KVM, cache e upload de artefatos; `ci.yml` cobre Python 3.12/3.13, sem emulador | Reutilizar o job existente nos PRs para `main` e impedir execução verde sem testes reais |
| [#55](https://github.com/desodre/Geppetto/issues/55) | MkDocs Material, mkdocstrings, quatro receitas, destaque a `py.typed`, publicado no Pages a partir de `main` | README e exemplo de login existem; não há configuração de MkDocs ou diretório de documentação; API do repositório informa `has_pages=false` | Criar conteúdo, referência, validação, implantação e verificar o site público |
| [#56](https://github.com/desodre/Geppetto/issues/56) | SemVer, depreciação por pelo menos uma minor, suporte Python/Android em docs e CONTRIBUTING | Versão centralizada e conferência de tag já existem; regras parciais em AGENTS; não existe CONTRIBUTING | Formalizar contrato, matriz de suporte e processo de release/depreciação |

As alterações locais da correção #62 pertencem a outro trabalho. Antes de implementar este plano,
preservá-las em sua branch e iniciar cada entrega em uma branch própria a partir de `main`.

## 2. Decisões propostas

- Ordem: **#54 → #56 → #55 → verificação final de #53**. A política poderá ser escrita enquanto o
  CI é ajustado, mas sua matriz final deve refletir os ambientes efetivamente validados.
- Idioma do conteúdo público: inglês, seguindo README, changelog e API atuais.
- Reaproveitar as suítes e o exemplo de login existentes. Não substituir a arquitetura da biblioteca.
- Dependências de documentação em um grupo `docs` do uv; nenhuma dependência de site no pacote
  instalado pelos usuários ou nos extras de execução.
- Manter MkDocs Material + mkdocstrings, conforme #55, com versões compatíveis fixadas em `uv.lock`.
  Fazer uma prova de build antes de escrever todo o conteúdo.
- Publicar o site de `main` por artefatos do GitHub Pages. PRs somente constroem e validam o site.
- Identificar o conteúdo de `main` como desenvolvimento/unreleased quando incluir APIs ainda não
  publicadas no PyPI; explicar como reproduzir os exemplos com o checkout correspondente.
- Adotar API 26 como mínimo de suporte proposto na #56 somente após validar um smoke nesse
  ambiente. API 34 continua a matriz completa em todo PR; o mínimo terá validação manual e
  por release, com limitações por recurso documentadas.

O Material for MkDocs anuncia fim de vida em **05/05/2027** e indica Zensical como sucessor.
Manter Markdown portável, poucas personalizações e registrar uma tarefa de migração antes dessa
data. Alterar a stack exigida na #55 seria uma mudança explícita de escopo, não uma decisão
silenciosa durante a implementação. [Fonte oficial](https://squidfunk.github.io/mkdocs-material/getting-started/).

## 3. Entrega 1 — #54: integração em todo PR para main

Branch proposta: `ci/emulator-pr-main-54`.

### Implementação

1. Extrair o job de emulador de `dev.yml` para `.github/workflows/integration.yml`, reutilizável
   via `workflow_call`, com opção de execução manual. Preservar API 34, `x86_64`, KVM, espera por
   boot, cache de AVD e limite total do job.
2. Fazer `ci.yml` chamar esse workflow em um job independente dos testes unitários. Seus gatilhos
   atuais já cobrem PR para `main`, push em `main` e chamada pelo workflow de publicação.
3. Simplificar `dev.yml` para chamar `ci.yml` uma única vez. Como a integração passa a fazer parte
   desse fluxo, remover o job duplicado de emulador. Evitar um ciclo de workflows reutilizáveis.
4. Preservar a relação `publish.yml: checks → build → publish`; com isso a publicação também
   dependerá da integração. Manter separados os tokens de validação e publicação.
5. Instalar com `uv sync --frozen --group dev --python 3.12`. Executar a suíte `integration/`
   existente contra `emulator-5554`, com JUnit e saída em `integration-results/`.
6. Acrescentar uma verificação anterior à suíte: serial selecionado deve estar pronto e responder
   a shell/boot. No CI, ausência do emulador deve falhar; o comportamento local de skip sem
   dispositivo continua disponível.
7. Verificar o JUnit para impedir sucesso quando não houve teste efetivamente executado.
   Permitir apenas skips documentados para capacidades específicas; API 34 deve exercitar
   os casos de crash que exigem Android 13+.
8. Subir JUnit e diagnósticos também quando a suíte falhar. Preservar screenshots, XML, logcat e
   vídeo de falhas; distinguir erro de boot, erro de instalação e falha da biblioteca.
9. Incluir API, arquitetura e configuração relevante na chave do cache; validar uma execução
   com cache vazio e outra com cache preenchido. Não mascarar falhas com reruns automáticos.
10. Permitir selecionar uma suíte de compatibilidade em API 26 no workflow reutilizável, para
    a validação inicial e antes de releases. Executar ADB, UI, CLI e artefatos aplicáveis; não
    depender de `am crash`, ausente nessa API. O fluxo de publicação deve exigir esse smoke
    além da integração completa API 34; no PR comum, API 34 mantém o custo limitado.
11. Atualizar README e AGENTS para refletir integração em `main`, `dev` e antes de publicação.
    Após obter os nomes finais dos checks, configurar a proteção de `main` para exigi-los.

### Cobertura e validação

- Reutilizar os casos reais de ADB, UI, timeout, CLI, gravação, artefatos do plugin, Inspector e
  detecção de crashes. Não criar outra suíte equivalente.
- Se houver código novo para validar o JUnit/ambiente, testar resultado sem casos, todos skipped,
  execução real e falha original preservada.
- Validar workflow e permissões; PRs de forks devem rodar com token de leitura, sem secrets.
- Executar emulador no PR e confirmar resultado real, serial e relatórios no run do GitHub.
- Testar o caminho de falha controlada na branch de trabalho, confirmar upload de artefatos e
  remover a falha intencional antes do merge.
- Validar que o workflow de publicação permanece bloqueado por falhas de integração, sem
  criar tag nem publicar um pacote para fazer esse teste.

### Concluído quando

- [ ] Todo PR para `main` dispara testes unitários e integração em API 34.
- [ ] Nenhum run sem emulador/testes reais é considerado sucesso.
- [ ] Não há execução duplicada de integração em `dev`.
- [ ] Cache vazio e cache preenchido funcionam; falhas deixam diagnósticos úteis.
- [ ] Smoke API 26 pode ser chamado e é exigido antes da publicação de releases.
- [ ] Check obrigatório de integração configurado e documentado.
- [ ] PR mesclado e evidências dos runs vinculadas à #54.

## 4. Entrega 2 — #56: contrato de compatibilidade e contribuição

Branch proposta: `docs/versioning-policy-56`.

### Implementação

1. Criar `CONTRIBUTING.md` com instalação, comandos de qualidade, testes com/sem dispositivo,
   fluxo issue/branch/PR, convenções de commit e checklist de revisão.
2. Usar CONTRIBUTING como fonte canônica da política, conforme o comentário da #56. Criar
   `docs/policies/versioning.md` incorporando a seção correspondente no build do site;
   evitar duas políticas independentes.
3. Definir API pública: símbolos exportados, APIs documentadas, CLI, fixtures/opções/markers
   do pytest e comportamentos de saída declarados como contrato. Módulos internos não recebem
   garantia implícita só por existirem.
4. Definir versões: patch para correção compatível; minor para funcionalidade compatível e início
   de depreciação; major para remoções e outras incompatibilidades.
   Basear o texto em [SemVer 2.0.0](https://semver.org/spec/v2.0.0.html).
5. Definir depreciação: `DeprecationWarning`, `stacklevel` apontando para o chamador, substituto,
   versão de início, versão mínima de remoção e entrada no changelog. Preservar a API durante
   pelo menos uma minor publicada e remover somente em major.
   Exemplo de política: deprecar em 2.2, manter em 2.3, remover no mínimo em 3.0.
6. Criar `geppetto._deprecation.warn_deprecated(old, new, since)` conforme proposto na issue,
   tipado e sem efeitos no import. Testar categoria, mensagem e localização do aviso passando
   por uma API intermediária: o stacklevel deve chegar ao usuário, não ao helper/wrapper.
   Não exportar o helper nem criar depreciações fictícias para exercitá-lo.
7. Auditar aliases e APIs já documentadas, incluindo `Direction.Up`/`Down`. Registrar seu estado
   real; não emitir novos avisos ou remover aliases apenas para demonstrar a política.
8. Publicar uma matriz honesta de suporte inicial:

   | Ambiente | Compromisso inicial |
   | --- | --- |
   | Python 3.12 e 3.13 | Suportados e testados em CI |
   | Python abaixo de 3.12 | Não suportado, conforme metadata |
   | Python mais recente | Não certificado até entrar na matriz; instalação permitida não equivale a homologação |
   | Android 8 / API 26 | Mínimo proposto no comentário da #56; exigir smoke real antes de assumir o compromisso |
   | Android 14 / API 34, emulador Linux x86_64 | Matriz completa de integração em todo PR |
   | Android API 26+ intermediários/mais recentes | Faixa de suporte pretendida; identificar explicitamente quais APIs foram testadas e quais recursos têm requisito maior |
   | OEMs e aparelhos físicos | Compatibilidade específica ainda não certificada; documentar evidências e limitações por recurso |
   | Fastboot, root, hardware e extras | Exigem capacidades/dependências específicas; não são provados pelo emulador padrão |

   Declarar requisitos por recurso, como `am crash` nos testes de Android 13+, sem confundir isso
   com o requisito mínimo global de Android. Se o smoke API 26 falhar por incompatibilidade real,
   corrigir a causa ou revisar a proposta da issue antes de anunciar suporte. Não descrever toda
   a faixa API 26+ como integralmente testada porque API 26 e API 34 passaram.
9. Documentar releases: `__version__` continua a única fonte; changelog de unreleased para versão;
   wheel/sdist; conferência `vX.Y.Z`; CI; publicação OIDC existente; smoke de instalação limpa.
   Não alterar versão, criar tag ou publicar durante a escrita desta política.
10. Tratar redução de suporte a Python/Android suportado como mudança de compatibilidade,
   com aviso e release major. Diferenciar limitações de permissões/OEM de quebra de API.
11. Incluir verificação de que o wheel contém `geppetto/py.typed` e um exemplo real de uso com
    mypy. Não criar um segundo arquivo que copie a versão.

### Concluído quando

- [ ] Política acessível em `docs/policies/versioning.md` e ligada em CONTRIBUTING/README.
- [ ] SemVer, depreciação, superfície pública e versões suportadas estão explícitos.
- [ ] Helper interno tem testes de mensagem/categoria/localização, sem alterar aliases existentes.
- [ ] A proposta API 26+ tem evidência do smoke mínimo e limitações documentadas.
- [ ] Matriz corresponde aos workflows, sem promessas não testadas.
- [ ] Checklist de release reutiliza o processo existente e verifica pacote tipado.
- [ ] Regra 6 de AGENTS aponta para a política longa em CONTRIBUTING.
- [ ] PR mesclado; publicação web da política fica coberta pela entrega #55.

## 5. Entrega 3 — #55: site, referência e receitas executáveis

Branch proposta: `docs/documentation-site-55`.

### Infraestrutura e navegação

1. Adicionar grupo `docs` em `pyproject.toml` com `mkdocs-material` e `mkdocstrings[python]`;
   atualizar `uv.lock`. Validar a combinação em Python 3.12 antes de fixar os intervalos.
2. Criar `mkdocs.yml`: navegação explícita, busca, blocos de código, links do repositório,
   `site_url` com o prefixo `/Geppetto/` e diretório de saída `site/` ignorado pelo Git.
3. Configurar coleta estática de fontes em `src`, com `allow_inspection: false`. Para objetos
   opcionais exportados por `__getattr__`, apontar para seus módulos de definição, sem instalar
   BrainStem/OpenCV ou conectar a dispositivos no build.
   [Configuração oficial do handler Python](https://mkdocstrings.github.io/python/usage/configuration/general/).
4. Criar esta estrutura de conteúdo; os nomes podem ser ajustados sem alterar o escopo:

   ```text
   docs/
     index.md
     getting-started.md
     guides/pytest.md
     guides/cli.md
     guides/inspector.md
     guides/logcat-and-crashes.md
     recipes/login.md
     recipes/boot-time.md
     recipes/two-devices.md
     recipes/failure-artifacts.md
     reference/device.md
     reference/ui-and-models.md
     reference/transport-and-services.md
     reference/recording-and-logcat.md
     reference/inspector.md
     reference/optional-features.md
     reference/exceptions.md
     policies/versioning.md
     contributing.md
     changelog.md
   ```

5. Explicar instalação base/extras, adb/fastboot, primeira instalação do agente uiautomator2,
   seleção de serial, permissões, erros e limites de recursos. Destacar `py.typed` na introdução
   e instalação, com exemplo de tipagem verificável.
6. Reaproveitar README como entrada curta. Site recebe tutoriais e referência; changelog e
   CONTRIBUTING devem ser incorporados de suas fontes canônicas ou ligados de forma explícita.
   Não manter cópias manuais que podem divergir.
7. Completar docstrings necessárias à referência com parâmetros, retorno e erros reais.
   Não prometer que APIs antigas encapsulam exceções que ainda deixam escapar.

### Quatro receitas obrigatórias

| Receita | Implementação planejada | Evidência de conclusão |
| --- | --- | --- |
| Login | Reutilizar `examples/pytest/test_login.py` e `login_app`; build, instalação e seleção de widgets; senha com `log_text=False` | App de demonstração instalado em emulador; fluxo termina autenticado; instruções reproduzíveis |
| Tempo de boot | Exemplo com `time.monotonic()`, espera por `sys.boot_completed`, timeout e relato do intervalo medido | Execução em emulador; unidade cobrindo cálculo/timeout apenas se houver lógica nova |
| Dois dispositivos | Usar `devices`, dois seriais explícitos e resultados identificados por serial; explicar requisito de dois dispositivos prontos | Validação de seleção por fakes e execução demonstrada em dois emuladores ou dispositivos de laboratório autorizados |
| Artefatos de falha | Reutilizar exemplo de `xfail`, HTML/JUnit, vídeo padrão, modos de captura e `crash.txt` quando aplicável | PNG/XML/logcat/MP4 reais e referências corretas nos relatórios; falha de captura preserva o resultado original |

Manter exemplos Python em arquivos executáveis e referenciá-los nas páginas. Não copiar blocos
grandes para que código e documentação evoluam separadamente. Login deve indicar JDK e SDK
exigidos pelo app de demonstração, que são distintos da API 34 do emulador.

Antes da receita de boot, revisar o limite total de `Device.reboot`: a chamada atual a
`AdbClient.wait_for_device()` não recebe timeout. Não anunciar um limite global que o código não
garante. Se necessário, tratar a correção em uma issue própria, com teste, como pré-requisito da
receita; este plano não expande a API de reboot por conveniência editorial.

### Validação e publicação

1. Criar `.github/workflows/docs.yml`, em PR para `main` e push em `main`, com instalação frozen
   do grupo docs e `mkdocs build --strict`. Usar os mesmos comandos no desenvolvimento local.
2. Verificar links internos, navegação e referências de API no build; checagem de links externos
   pode rodar separadamente para não bloquear todo PR por indisponibilidade de terceiros.
3. Validar os arquivos de exemplo por compilação/lint e sua lógica com os testes existentes.
   Executar receitas de um dispositivo em emulador; para dois dispositivos, usar uma execução
   dedicada manual ou de laboratório, sem duplicar emuladores em todos os PRs.
4. Após merge, build publica artefato; job de deploy depende dele, usa ambiente `github-pages`,
   `pages: write` e `id-token: write`. Apenas esse job recebe permissões de publicação, e apenas
   código de `main` pode chegar a ele.
   [Fluxo oficial do GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
5. Habilitar Pages com origem GitHub Actions e configurar ambiente/branch. A publicação será
   uma etapa explícita da implementação, depois de o site estar revisável; não faz parte da
   criação deste plano.
6. Usar `https://desodre.github.io/Geppetto/` como URL prevista, confirmando a URL efetiva devolvida
   pelo deploy. Atualizar README e `project.urls.Documentation` depois dessa confirmação.
7. Verificar página inicial, busca, navegação mobile, referências, quatro receitas e URLs com
   prefixo do repositório. Confirmar HTTP 200 e ausência de assets/links locais quebrados.
8. Mostrar a política #56 e a distinção entre desenvolvimento e pacote publicado no PyPI.
   Versionamento simultâneo de múltiplos sites não é requisito desta issue.

### Concluído quando

- [ ] Build estrito passa em PR sem dispositivo e sem extras opcionais da biblioteca.
- [ ] Referência cobre a API pública e resolve os exports opcionais corretamente.
- [ ] As quatro receitas estão documentadas e têm evidências de execução.
- [ ] `py.typed` está visível e foi verificado no pacote construído.
- [ ] Site publicado a partir de `main`, URL pública conferida e links do projeto atualizados.
- [ ] Política #56, contribuição e changelog estão acessíveis.
- [ ] Risco de fim de vida do tema tem acompanhamento antes de maio de 2027.

## 6. Sequência de PRs e rastreamento

| Ordem | PR | Dependências | Issue que pode encerrar |
| --- | --- | --- | --- |
| 1 | Emulador reutilizável e integração obrigatória em main | Suíte existente | #54, depois das evidências de CI |
| 2 | SemVer, suporte, helper de depreciação e CONTRIBUTING | Matriz e smoke API 26 validados pelo PR 1 | #56 |
| 3 | Site, referência, receitas e workflow Pages | PR 2; validação do boot e das receitas | #55 somente após publicação real |
| 4, se necessário | Links finais e registro das evidências públicas | Deploy bem-sucedido do PR 3 | #55 e, após auditoria global, #53 |

Em cada entrega, mover somente a issue correspondente para In Progress, atualizar CHANGELOG
quando houver mudança visível e AGENTS quando o fluxo mudar. Fazer commits convencionais em
inglês e PRs para `main`.

**Cuidado com o fechamento automático:** o workflow atual fecha issues citadas como `Refs #N`,
`Closes #N` ou sufixo `(#N)` e também suas subissues. Não usar essas formas para #53 em commits
ou PRs parciais. Usar um link comum ou `Part of #53` para contexto. Na #55, não usar uma
referência de fechamento antes de confirmar o deploy; a issue pode ser encerrada na entrega
final de links/evidências. Nunca fechar a parent só porque o código dos workflows foi mesclado.

## 7. Validação conjunta e encerramento da parent

Executar os checks obrigatórios, mais o build da documentação e dos pacotes:

```bash
uv sync --frozen --group dev --group docs
uv run ruff check src tests integration
uv run ruff format --check src tests integration
uv run mypy src
uv run pytest
uv run mkdocs build --strict
uv build
```

Rodar integração no emulador configurado pelo CI e registrar uma demonstração de dois
dispositivos. Verificar o wheel e uma instalação limpa sem extras; execução de docs não deve
iniciar adb, instalar agentes ou carregar dependências de hardware.

Encerrar #53 somente quando:

- [ ] #54, #55 e #56 atingiram seus critérios e foram encerradas.
- [ ] Um PR para `main` demonstrou integração real, não apenas coleta ou skips.
- [ ] O site público está disponível e as quatro receitas foram verificadas.
- [ ] A política de suporte corresponde à matriz real de CI e ao processo de release.
- [ ] README, site, CONTRIBUTING, AGENTS e metadata apontam para o mesmo fluxo.
- [ ] Evidências dos runs, URL do Pages e resultados das receitas estão ligadas às issues.

## 8. Riscos e limites

- Emulador: KVM, boot e cache podem falhar; diagnóstico e falha explícita são parte da entrega.
- Estado compartilhado: testes de Settings, gravação e crash devem restaurar o necessário e
  não depender de ordem acidental. Manter observação de crashes restrita aos pacotes selecionados.
- Receitas: reboot e dois dispositivos exigem ambientes próprios; não declarar execução que
  ocorreu apenas com fakes.
- Publicação: configuração do Pages e proteção de branch dependem de acesso administrativo.
  Preparar conteúdo e workflows antes dessa etapa; verificar a configuração efetiva.
- Documentação gerada: resolver fontes estáticas e exports lazy antes de escrever toda a API.
- Suporte: um emulador API 34 não certifica API 26, OEMs ou hardware físico; o mínimo API 26
  proposto na #56 precisa de evidência própria e não substitui testes de todos os recursos.
- Manutenção do tema: stack exigida pela #55 tem data anunciada de fim de vida; acompanhar migração.

Não fazem parte desta entrega: novos recursos de automação, suporte certificado a todos os
Androids/Pythons, farm de dispositivos, publicação de release no PyPI ou redesign do Inspector.
