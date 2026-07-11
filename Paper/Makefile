MAIN_TEX ?= 0.Main

.PHONY: all clean

all:
	pdflatex -interaction=nonstopmode $(MAIN_TEX).tex
	bibtex $(MAIN_TEX) || true
	pdflatex -interaction=nonstopmode $(MAIN_TEX).tex
	pdflatex -interaction=nonstopmode $(MAIN_TEX).tex

clean:
	rm -f *.aux *.bbl *.blg *.log *.out *.toc *.fls *.fdb_latexmk
