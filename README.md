# Red Neuronal desde Cero: Reconocimiento de Dígitos (MNIST)

Implementación de una red neuronal feedforward que clasifica dígitos escritos a mano (0-9) del dataset MNIST, construida en dos versiones:

1. `src/scratch/` — Desde cero con NumPy puro: forward pass, backpropagation y descenso de gradiente estocástico implementados manualmente.
2. `src/pytorch_version/` — La misma arquitectura usando PyTorch, como comparación.

Proyecto realizado siguiendo la serie de 3Blue1Brown "Neural Networks" y el libro de Michael Nielsen "Neural Networks and Deep Learning".

## Arquitectura

- Entrada: 784 neuronas (imagen 28x28 aplanada)
- Capa oculta 1: 16 neuronas
- Capa oculta 2: 16 neuronas
- Salida: 10 neuronas (dígitos 0-9)

## Instalación

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

## Estado

Proyecto en construcción. Próximos pasos: implementar carga de datos y red neuronal.
