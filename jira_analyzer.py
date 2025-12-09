import matplotlib.pyplot as plt
# import matplotlib.dates as mdates 
from datetime import datetime
from collections import defaultdict
import requests
import numpy as np
import json


try:
    with open('config.json', 'r') as f:
        config = json.load(f)
        
        # Берем значения из файла, если их нет - используем дефолтные
        JIRA_URL = config.get("jira_url", "https://issues.apache.org/jira")
        PROJECT = config.get("default_project", "KAFKA")
        MAX_RESULTS = config.get("max_results", 50)  
        TIMEOUT = config.get("timeout", 30)           

except FileNotFoundError:
    print("Файл config.json не найден.")
    JIRA_URL = "https://issues.apache.org/jira"
    PROJECT = "KAFKA"
    MAX_RESULTS = 50
    TIMEOUT = 30


def get_jira_issues():
    issues = []
    start_at = 0
    
    while True:
        params = {
            "jql": f"project={PROJECT} AND status in (Closed, Resolved)",
            "startAt": start_at,
            "maxResults": MAX_RESULTS,
            "fields": "key,created,resolutiondate,status,reporter,assignee,priority,timespent,summary"
        }
        
        try:
            resp = requests.get(f"{JIRA_URL}/rest/api/2/search", params=params, timeout=TIMEOUT)
            data = resp.json()
        except Exception as e:
            print(f"Ошибка при запросе: {e}")
            break
        
        page_issues = data.get("issues", [])
        if not page_issues:
            break
        
        issues.extend(page_issues)
        print(f"Получено {len(page_issues)} задач, всего собрано: {len(issues)}")
        
        if len(page_issues) < MAX_RESULTS:
            break
        
        start_at += len(page_issues)
    
    print(f"Всего загружено задач: {len(issues)}")
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
    """График заведенных и закрытых задач за последний год"""
    from datetime import datetime, timedelta
    
    created_dates = defaultdict(int)
    closed_dates = defaultdict(int)
    
    one_year_ago = datetime.now().date() - timedelta(days=365)
    
    for issue in issues:
        created_date = datetime.strptime(issue['fields']['created'].split('.')[0], '%Y-%m-%dT%H:%M:%S').date()
        if created_date >= one_year_ago:
            created_dates[created_date] += 1
        
        if issue['fields'].get('resolutiondate'):
            closed_date = datetime.strptime(issue['fields']['resolutiondate'].split('.')[0], '%Y-%m-%dT%H:%M:%S').date()
            if closed_date >= one_year_ago:
                closed_dates[closed_date] += 1
    
    dates = sorted(set(created_dates.keys()) | set(closed_dates.keys()))
    created_counts = [created_dates.get(date, 0) for date in dates]
    closed_counts = [closed_dates.get(date, 0) for date in dates]
    
    created_cumsum = np.cumsum(created_counts)
    closed_cumsum = np.cumsum(closed_counts)
    
    # Создаем 2 подграфика
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
    
    # График 1: За день
    ax1.plot(dates, created_counts, label='Создано за день', marker='o', color='#2E86AB', linewidth=1.5)
    ax1.plot(dates, closed_counts, label='Закрыто за день', marker='s', color='#F18F01', linewidth=1.5)
    ax1.set_ylabel('Количество задач')
    ax1.set_title('Задачи созданные и закрытые за день')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # График 2: Накопительно
    ax2.plot(dates, created_cumsum, label='Создано (накопительно)', color='#2E86AB', linewidth=2, linestyle='--')
    ax2.plot(dates, closed_cumsum, label='Закрыто (накопительно)', color='#F18F01', linewidth=2, linestyle='--')
    ax2.set_xlabel('Дата')
    ax2.set_ylabel('Накопительное количество задач')
    ax2.set_title('Накопительный итог задач')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # Поворот подписей дат
    for ax in [ax1, ax2]:
        ax.tick_params(axis='x', rotation=45)
    
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
    
    top_users = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:30]
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