# Статья о платформе «Кадровый ассистент»

`kadry-paper.pdf` — научно-инженерная статья об архитектуре, пайплайне оценки с верификацией цитат, сравнении поиска BM25 и E5, модели полноты отчётности, алгоритме Куна и экспериментальных замерах системы (по состоянию репозитория `c87cbd6`).

Исходник — [`kadry-paper.tex`](kadry-paper.tex). Графики в `figures/` пересобираются строго из сохранённых JSON-отчётов репозитория (`docs/reports/` и `docs/modules/search-evaluation-v1.json`) скриптом [`build_figures.py`](build_figures.py):

```bash
python docs/paper/build_figures.py
cd docs/paper
tectonic kadry-paper.tex
```

Сборка PDF выполняется через [Tectonic](https://tectonic-typesetting.github.io) (недостающие пакеты LaTeX скачиваются автоматически).
