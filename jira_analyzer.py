import matplotlib.pyplot as plt
# import matplotlib.dates as mdates 
from datetime import datetime
from collections import defaultdict
import requests
import numpy as np
import json

# JIRA_URL = "https://issues.apache.org/jira"
# PROJECT = "KAFKA"
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
        
        # Берем значения из файла, если их нет - используем дефолтные
        JIRA_URL = config.get("jira_url", "https://issues.apache.org/jira")
        PROJECT = config.get("default_project", "KAFKA")
        MAX_RESULTS = config.get("max_results", 50)  
        TIMEOUT = config.get("timeout", 30)           

except FileNotFoundError:
    print("Внимание: Файл config.json не найден! Используются настройки по умолчанию.")
    JIRA_URL = "https://issues.apache.org/jira"
    PROJECT = "KAFKA"
    MAX_RESULTS = 50
    TIMEOUT = 30
# def get_jira_issues():
#     url = f"{JIRA_URL}/rest/api/2/search"
#     params = {
#         "jql": f"project={PROJECT} AND status in (Closed, Resolved)",
#         "maxResults": 100,
#         "fields": "key,created,resolutiondate,status,reporter,assignee,priority,timespent,summary"
#     }
    
#     try:
#         response = requests.get(url, params=params, timeout=15)
#         data = response.json()
#         return data.get("issues", [])
#     except:
#         return []

def get_jira_issues():
    # 1. Получаем 50 задач "Closed"
    print("Запрос 50 задач Closed...")
    params_closed = {
        "jql": f"project={PROJECT} AND status = Closed",
        "maxResults": MAX_RESULTS,
        "fields": "key,created,resolutiondate,status,reporter,assignee,priority,timespent,summary"
    }
    
    # 2. Получаем 50 задач "Resolved"
    print("Запрос 50 задач Resolved...")
    params_resolved = {
        "jql": f"project={PROJECT} AND status = Resolved",
        "maxResults": MAX_RESULTS,
        "fields": "key,created,resolutiondate,status,reporter,assignee,priority,timespent,summary"
    }
    
    issues = []
    
    # Выполняем 1-й запрос
    try:
        resp1 = requests.get(f"{JIRA_URL}/rest/api/2/search", params=params_closed, timeout=TIMEOUT)
        data1 = resp1.json()
        issues.extend(data1.get("issues", []))
    except Exception as e:
        print("Ошибка при получении Closed:", e)

    # Выполняем 2-й запрос
    try:
        resp2 = requests.get(f"{JIRA_URL}/rest/api/2/search", params=params_resolved, timeout=TIMEOUT)
        data2 = resp2.json()
        issues.extend(data2.get("issues", []))
    except Exception as e:
        print("Ошибка при получении Resolved:", e)

    return issues


def calculate_time(created_str, resolved_str):
    created = datetime.strptime(created_str.split('.')[0], '%Y-%m-%dT%H:%M:%S')
    resolved = datetime.strptime(resolved_str.split('.')[0], '%Y-%m-%dT%H:%M:%S')
    return (resolved - created).days

def task_1(issues):
    """Гистограмма времени в открытом состоянии"""
    times = []
    for issue in issues:
        if issue['fields'].get('resolutiondate'):
            days = calculate_time(issue['fields']['created'], issue['fields']['resolutiondate'])
            times.append(days)
    
    plt.figure(figsize=(10, 6))
    plt.hist(times, bins=15, range=(0, 60), edgecolor='black', alpha=0.7, color='#2E86AB')
    plt.xlabel('Дни в открытом состоянии')
    plt.ylabel('Количество задач')
    plt.title('Гистограмма времени в открытом состоянии')
    plt.grid(True, alpha=0.3)
    plt.show()

def task_2(issues):
    """Распределение времени по состояниям"""
    status_groups = defaultdict(list)
    for issue in issues:
        status = issue['fields']['status']['name']
        if issue['fields'].get('resolutiondate'):
            days = calculate_time(issue['fields']['created'], issue['fields']['resolutiondate'])
            status_groups[status].append(days)
    
    colors = ['#3498db', '#27ae60', '#f39c12', '#9b59b6', '#e74c3c']
    for i, (status, times) in enumerate(list(status_groups.items())[:5]):
        print(f"Статус '{status}': найдено {len(times)} задач для построения графика.")
        plt.figure(figsize=(10, 5))
        plt.hist(times, bins=10, range=(0, 60), alpha=0.7, color=colors[i], edgecolor='black')
        plt.xlabel(f'Дни в состоянии {status}')
        plt.ylabel('Количество задач')
        plt.title(f'Распределение времени в состоянии {status}')
        plt.grid(True, alpha=0.3)
        plt.show()

def task_3(issues):
    """График заведенных и закрытых задач"""
    created_dates = defaultdict(int)
    closed_dates = defaultdict(int)

    for issue in issues:
        created_date = datetime.strptime(issue['fields']['created'].split('.')[0], '%Y-%m-%dT%H:%M:%S').date()
        created_dates[created_date] += 1
        if issue['fields'].get('resolutiondate'):
            closed_date = datetime.strptime(issue['fields']['resolutiondate'].split('.')[0], '%Y-%m-%dT%H:%M:%S').date()
            closed_dates[closed_date] += 1

    dates = sorted(set(created_dates.keys()) | set(closed_dates.keys()))
    created_counts = [created_dates.get(date, 0) for date in dates]
    closed_counts = [closed_dates.get(date, 0) for date in dates]

    plt.figure(figsize=(12, 6))
    plt.plot(dates, created_counts, label='Создано', marker='o')
    plt.plot(dates, closed_counts, label='Закрыто', marker='s')
    plt.xlabel('Дата')
    plt.ylabel('Количество задач')
    plt.title('График заведенных и закрытых задач')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()




def task_4(issues):
    """Топ пользователей"""
    user_counts = defaultdict(int)
    for issue in issues:
        if issue['fields'].get('assignee'):
            user_counts[issue['fields']['assignee'].get('displayName', 'Unknown')] += 1
        if issue['fields'].get('reporter'):
            user_counts[issue['fields']['reporter'].get('displayName', 'Unknown')] += 1
    
    top_users = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:15]
    users, counts = zip(*top_users) if top_users else ([], [])
    
    plt.figure(figsize=(10, 6))
    plt.barh(users, counts, color='#2E86AB', alpha=0.7)
    plt.xlabel('Количество задач')
    plt.ylabel('Пользователи')
    plt.title('Топ пользователей по количеству задач')
    plt.gca().invert_yaxis()
    plt.grid(True, alpha=0.3, axis='x')
    plt.tight_layout()
    plt.show()

def task_5(issues):
    """Гистограмма затраченного времени"""
    times = []
    for issue in issues:
        if issue['fields'].get('timespent'):
            # Конвертируем секунды в дни
            days = issue['fields']['timespent'] / 86400
            times.append(days)
        elif issue['fields'].get('resolutiondate'):
            # Используем разницу дат если нет logged time
            days = calculate_time(issue['fields']['created'], issue['fields']['resolutiondate'])
            times.append(days)
    
    plt.figure(figsize=(10, 6))
    if times:
        plt.hist(times, bins=15, range=(0, 60), edgecolor='black', alpha=0.7, color='#A23B72')
        plt.xlabel('Затраченное время (дни)')
    else:
        plt.text(0.5, 0.5, 'Нет данных', ha='center', va='center', transform=plt.gca().transAxes)
    plt.ylabel('Количество задач')
    plt.title('Гистограмма затраченного времени')
    plt.grid(True, alpha=0.3)
    plt.show()

def task_6(issues):
    """Распределение по приоритетам"""
    priorities = defaultdict(int)
    for issue in issues:
        priority = issue['fields'].get('priority', {}).get('name', 'Не указан')
        priorities[priority] += 1
    
    plt.figure(figsize=(8, 5))
    plt.bar(priorities.keys(), priorities.values(), color='#2E86AB', alpha=0.7)
    plt.xlabel('Приоритет')
    plt.ylabel('Количество задач')
    plt.title('Распределение задач по приоритетам')
    plt.grid(True, alpha=0.3, axis='y')
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()

def main():
    print("JIRA Analytics для проекта", PROJECT)
    issues = get_jira_issues()
    print(f"Всего получено задач из JIRA: {len(issues)}") 
    if not issues:
        print("Нет данных")
        return
    
    task_1(issues)  # Гистограмма времени
    task_2(issues)  # Распределение по состояниям
    task_3(issues)  # График задач по дням
    task_4(issues)  # Топ пользователей
    task_5(issues)  # Затраченное время
    task_6(issues)  # Приоритеты
    
    print("Все графики построены!")

if __name__ == "__main__":
    main()