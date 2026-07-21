"""
train.py

Entrena la red con PyTorch y guarda los resultados (historial de
precision, el modelo entrenado, predicciones sobre el test set) en
la carpeta results/, para que visualize.py los pueda usar despues.
"""

import json
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import datasets, transforms

from model import Network

# Rutas absolutas basadas en la ubicacion de este archivo, para que
# funcionen sin importar desde donde ejecutes el script.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RESULTS_DIR = PROJECT_ROOT / "results"


def load_data():
    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Lambda(lambda x: x.view(-1))
    ])
    train_dataset = datasets.MNIST(root=str(DATA_DIR), train=True, download=True, transform=transform)
    test_dataset = datasets.MNIST(root=str(DATA_DIR), train=False, download=True, transform=transform)
    return train_dataset, test_dataset


def evaluate(model, loader, device):
    model.eval()
    correct = 0
    total = 0
    with torch.no_grad():
        for x, y in loader:
            x, y = x.to(device), y.to(device)
            outputs = model(x)
            predictions = outputs.argmax(dim=1)
            correct += (predictions == y).sum().item()
            total += y.size(0)
    return correct, total


def evaluate_with_predictions(model, loader, device):
    """Igual que evaluate(), pero ademas devuelve todas las predicciones
    y etiquetas reales, para la matriz de confusion despues."""
    model.eval()
    all_true = []
    all_pred = []
    with torch.no_grad():
        for x, y in loader:
            x, y = x.to(device), y.to(device)
            preds = model(x).argmax(dim=1)
            all_true.extend(y.cpu().tolist())
            all_pred.extend(preds.cpu().tolist())
    return all_true, all_pred


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Usando dispositivo: {device}")

    train_dataset, test_dataset = load_data()
    train_loader = DataLoader(train_dataset, batch_size=10, shuffle=True)
    test_loader = DataLoader(test_dataset, batch_size=1000, shuffle=False)

    model = Network().to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.SGD(model.parameters(), lr=0.1)

    epochs = 30
    history = []

    for epoch in range(epochs):
        model.train()
        for x, y in train_loader:
            x, y = x.to(device), y.to(device)

            optimizer.zero_grad()
            outputs = model(x)
            loss = criterion(outputs, y)
            loss.backward()
            optimizer.step()

        correct, total = evaluate(model, test_loader, device)
        accuracy = correct / total
        history.append(accuracy)
        print(f"Epoca {epoch+1}/{epochs}: {correct}/{total} correctos ({100*accuracy:.2f}%)")

    print("Entrenamiento terminado. Calculando predicciones finales...")
    y_true, y_pred = evaluate_with_predictions(model, test_loader, device)

    print(f"Guardando resultados en {RESULTS_DIR} ...")
    torch.save(model.state_dict(), RESULTS_DIR / "pytorch_model.pt")
    with open(RESULTS_DIR / "pytorch_results.json", "w") as f:
        json.dump({"history": history, "y_true": y_true, "y_pred": y_pred}, f)
    print("Listo.")


if __name__ == "__main__":
    main()