import discord
from discord import app_commands
import json
import os
import asyncio
import re
from datetime import datetime, timedelta
from collections import defaultdict

# ===== НАСТРОЙКА БОТА =====
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class MyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ Слеш-команды синхронизированы")

bot = MyBot()

# ===== СИСТЕМА МОДЕРАЦИИ PHANTOM VORTEX =====
class PhantomVortexModSystem:
    def __init__(self):
        self.user_warnings = defaultdict(int)
        self.warning_timestamps = defaultdict(list)
        self.spam_detection = defaultdict(list)
    
    async def analyze_message(self, message):
        if message.author.bot:
            return None
        
        violations = []
        
        # Уровень 4: Критические нарушения
        if await self.check_level4_violations(message):
            return "LEVEL4"
        
        # Уровень 3: Серьезные нарушения
        if await self.check_level3_violations(message):
            violations.append("LEVEL3")
        
        # Уровень 2: Средние нарушения
        if await self.check_level2_violations(message):
            violations.append("LEVEL2")
        
        # Уровень 1: Легкие нарушения
        if await self.check_level1_violations(message):
            violations.append("LEVEL1")
        
        return violations[0] if violations else None
    
    async def check_level4_violations(self, message):
        content = message.content.lower()
        threats = ['убью', 'зарежу', 'изобью', 'вешайся', 'суицид', 'сдохни']
        discrimination = ['нигер', 'ниггер', 'чурка', 'хач', 'жид', 'пидорас']
        
        if (any(threat in content for threat in threats) or 
            any(disc_word in content for disc_word in discrimination) or
            re.search(r'\b\d{11,}\b', content)):
            return True
        return False
    
    async def check_level3_violations(self, message):
        content = message.content.lower()
        personal_insults = ['мудак', 'мудила', 'дебил', 'долбоёб', 'ублюдок', 'говноед']
        advertising = ['подписывайся', 'мой канал', 'купить', 'продам', 'реклама']
        
        if (any(insult in content for insult in personal_insults) or
            any(ad in content for ad in advertising) or
            await self.detect_targeted_trolling(message)):
            return True
        return False
    
    async def check_level2_violations(self, message):
        content = message.content.lower()
        nsfw_words = ['секс', 'порно', 'голый', 'обнаженный']
        cheat_words = ['читы', 'читер', 'взлом', 'паблик чит']
        mentions = message.mentions + message.role_mentions
        
        if (any(nsfw in content for nsfw in nsfw_words) or
            any(cheat in content for cheat in cheat_words) or
            len(mentions) >= 3):
            return True
        return False
    
    async def check_level1_violations(self, message):
        if await self.detect_spam(message) or await self.detect_off_topic(message):
            return True
        return False
    
    async def detect_spam(self, message):
        user_id = message.author.id
        now = datetime.now()
        self.spam_detection[user_id].append(now)
        self.spam_detection[user_id] = [t for t in self.spam_detection[user_id] if now - t < timedelta(seconds=10)]
        return len(self.spam_detection[user_id]) >= 5
    
    async def detect_targeted_trolling(self, message):
        if message.reference:
            try:
                replied_msg = await message.channel.fetch_message(message.reference.message_id)
                if replied_msg.author != message.author:
                    negative_words = ['дурак', 'идиот', 'тупой', 'слабый']
                    return any(word in message.content.lower() for word in negative_words)
            except:
                pass
        return False
    
    async def detect_off_topic(self, message):
        channel_name = message.channel.name.lower()
        if 'музыка' in channel_name and not await self.is_music_related(message.content):
            return True
        return False
    
    async def is_music_related(self, content):
        music_words = ['песня', 'трек', 'альбом', 'музыка', 'слушать']
        return any(word in content.lower() for word in music_words)
    
    async def apply_punishment(self, user, violation_level, channel, reason=""):
        user_id = user.id
        now = datetime.now()
        
        self.warning_timestamps[user_id].append(now)
        self.warning_timestamps[user_id] = [t for t in self.warning_timestamps[user_id] if now - t < timedelta(days=10)]
        active_warns = len(self.warning_timestamps[user_id])
        
        log_channel = discord.utils.get(channel.guild.channels, name="📋-логи-модерации")
        if not log_channel:
            overwrites = {channel.guild.default_role: discord.PermissionOverwrite(read_messages=False)}
            log_channel = await channel.guild.create_text_channel("📋-логи-модерации", overwrites=overwrites)
        
        embed = discord.Embed(title="🚨 Нарушение правил", color=0xe74c3c, timestamp=now)
        embed.add_field(name="Участник", value=user.mention, inline=True)
        embed.add_field(name="Уровень", value=violation_level, inline=True)
        embed.add_field(name="Активные варны", value=f"{active_warns}/3", inline=True)
        embed.add_field(name="Причина", value=reason or "Автомодерация", inline=False)
        
        if violation_level == "LEVEL4":
            try:
                await user.ban(reason=f"Критическое нарушение: {reason}")
                embed.add_field(name="Наказание", value="🔨 Пермабан", inline=False)
            except:
                embed.add_field(name="Ошибка", value="Не удалось забанить", inline=False)
        
        elif violation_level == "LEVEL3":
            for _ in range(2):
                self.warning_timestamps[user_id].append(now)
            try:
                await user.timeout(timedelta(days=3), reason=f"Серьезное нарушение: {reason}")
                embed.add_field(name="Наказание", value="🔇 Мут 3 дня + 2 варна", inline=False)
            except:
                embed.add_field(name="Наказание", value="2 варна", inline=False)
        
        elif violation_level == "LEVEL2":
            try:
                await user.timeout(timedelta(hours=6), reason=f"Среднее нарушение: {reason}")
                embed.add_field(name="Наказание", value="🔇 Мут 6 часов + варн", inline=False)
            except:
                embed.add_field(name="Наказание", value="1 варн", inline=False)
        
        elif violation_level == "LEVEL1":
            embed.add_field(name="Наказание", value="⚠️ Предупреждение", inline=False)
        
        if active_warns >= 3:
            try:
                await user.ban(reason="Автобан: 3 активных предупреждения")
                embed.add_field(name="🔨 Автобан", value="3 активных варна", inline=False)
            except:
                pass
        
        await log_channel.send(embed=embed)
        
        if violation_level in ["LEVEL2", "LEVEL3", "LEVEL4"]:
            await channel.send(f"🚨 {user.mention} получил наказание. Детали в {log_channel.mention}")

mod_system = PhantomVortexModSystem()

# ===== СИСТЕМА СОХРАНЕНИЯ КОМАНД =====
def load_teams():
    if os.path.exists('teams.json'):
        try:
            with open('teams.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_teams():
    with open('teams.json', 'w', encoding='utf-8') as f:
        json.dump(registered_teams, f, ensure_ascii=False, indent=2)

registered_teams = load_teams()

# ===== ИСПРАВЛЕННАЯ СИСТЕМА КЛОЗОВ =====
class MainPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label='📝 Регистрация команды', style=discord.ButtonStyle.primary, custom_id='register_btn')
    async def register_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RegistrationModal())
    
    @discord.ui.button(label='🎮 Создать клоз', style=discord.ButtonStyle.success, custom_id='create_clash_btn')
    async def create_clash(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        if user_id not in registered_teams:
            await interaction.response.send_message("❌ Сначала зарегистрируйте команду!", ephemeral=True)
            return
        
        # Проверяем активные клозы
        for category in interaction.guild.categories:
            team_name = registered_teams[user_id]
            if f"⚔️ {team_name}" in category.name:
                await interaction.response.send_message("❌ У вашей команды уже есть активный клоз!", ephemeral=True)
                return
        
        team_name = registered_teams[user_id]
        await self.create_clash_channels(interaction, team_name)
    
    @discord.ui.button(label='📊 Список команд', style=discord.ButtonStyle.secondary, custom_id='teams_list_btn')
    async def show_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not registered_teams:
            embed = discord.Embed(title="📊 Список команд", description="Пока никто не зарегистрировался", color=0xf39c12)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        teams_list = "\n".join([f"• **{name}**" for name in registered_teams.values()])
        embed = discord.Embed(title="📊 Зарегистрированные команды", description=teams_list, color=0x2ecc71)
        embed.add_field(name="📈 Статистика:", value=f"Всего команд: **{len(registered_teams)}**", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def create_clash_channels(self, interaction: discord.Interaction, team_name: str):
        """Создает клоз для команды против команды"""
        # Создаём категорию с названием команды
        category = await interaction.guild.create_category_channel(name=f"⚔️ {team_name}", position=0)
        
        # Настройки прав - доступ только для создателя
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False, connect=False),
            interaction.user: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, connect=True, manage_channels=True
            ),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, connect=True)
        }
        
        # Текстовый канал для переговоров
        text_channel = await category.create_text_channel(name="💬-переговоры", overwrites=overwrites)
        
        # ДВА голосовых канала для команд
        voice_team1 = await category.create_voice_channel(
            name=f"🔊 {team_name}", 
            overwrites=overwrites,
            user_limit=5  # 5 игроков в команде
        )
        
        voice_team2 = await category.create_voice_channel(
            name="🔊 Команда противника", 
            overwrites=overwrites,
            user_limit=5  # 5 игроков в команде
        )
        
        # Информационное сообщение
        embed = discord.Embed(
            title=f"⚔️ Клоз создан: {team_name}",
            description="**Для игры команда против команды:**",
            color=0x9b59b6
        )
        embed.add_field(
            name="🎯 Как играть:",
            value="• Пригласите свою команду в ваш войс-канал\n• Соперник подключается в канал 'Команда противника'\n• Договаривайтесь о матче в текстовом чате",
            inline=False
        )
        embed.add_field(
            name="🔧 Управление:",
            value="• Приглашайте участников правым кликом на канал\n• Клоз автоматически удалится через 2 часа",
            inline=False
        )
        
        await text_channel.send(
            content=f"👋 {interaction.user.mention}, клоз для команды **{team_name}** создан!",
            embed=embed
        )
        
        await interaction.response.send_message(
            f"✅ Клоз создан! {text_channel.mention}\n"
            f"• {voice_team1.mention} - ваша команда\n"
            f"• {voice_team2.mention} - команда противника", 
            ephemeral=True
        )
        
        # Автоудаление через 2 часа
        asyncio.create_task(delete_empty_clash(category, 7200))

# ===== ПАНЕЛЬ МОДЕРАЦИИ =====
class AdminPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label='👁️ Просмотреть заявки', style=discord.ButtonStyle.primary, custom_id='view_apps_btn')
    async def view_applications(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not registered_teams:
            await interaction.response.send_message("❌ Нет зарегистрированных команд.", ephemeral=True)
            return
        
        embed = discord.Embed(title="📋 Все зарегистрированные команды", color=0x3498db)
        for user_id, team_name in registered_teams.items():
            user = await bot.fetch_user(int(user_id))
            username = user.name if user else "Неизвестный"
            embed.add_field(name=f"🏷️ {team_name}", value=f"Капитан: {username}", inline=False)
        
        embed.set_footer(text=f"Всего команд: {len(registered_teams)}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label='📤 Экспорт в файл', style=discord.ButtonStyle.secondary, custom_id='export_btn')
    async def export_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not registered_teams:
            await interaction.response.send_message("❌ Нет данных для экспорта.", ephemeral=True)
            return
        
        filename = f"teams_export_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            for user_id, team_name in registered_teams.items():
                user = await bot.fetch_user(int(user_id))
                username = user.name if user else "Неизвестный"
                f.write(f"Команда: {team_name} | Капитан: {username}\n")
        
        await interaction.response.send_message(file=discord.File(filename), ephemeral=True)
        os.remove(filename)
    
    @discord.ui.button(label='🗑️ Очистить заявки', style=discord.ButtonStyle.danger, custom_id='clear_btn')
    async def clear_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not registered_teams:
            await interaction.response.send_message("❌ Нет данных для очистки.", ephemeral=True)
            return
        
        confirm_view = ConfirmClearView()
        await interaction.response.send_message("⚠️ Удалить ВСЕ зарегистрированные команды?", view=confirm_view, ephemeral=True)

class ConfirmClearView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)
    
    @discord.ui.button(label='✅ Да', style=discord.ButtonStyle.danger)
    async def confirm_clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        global registered_teams
        count = len(registered_teams)
        registered_teams = {}
        save_teams()
        await interaction.response.send_message(f"✅ Удалено {count} команд!", ephemeral=True)
    
    @discord.ui.button(label='❌ Нет', style=discord.ButtonStyle.secondary)
    async def cancel_clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Очистка отменена.", ephemeral=True)

# ===== МОДАЛЬНЫЕ ОКНА И ФУНКЦИИ =====
class RegistrationModal(discord.ui.Modal, title='📝 Регистрация команды'):
    team_name = discord.ui.TextInput(label='Название команды', placeholder='Введите название команды...', max_length=50)
    captain_name = discord.ui.TextInput(label='Имя капитана', placeholder='Ваш игровой никнейм...', max_length=30)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        if user_id in registered_teams:
            await interaction.response.send_message(f"❌ Вы уже зарегистрированы как **{registered_teams[user_id]}**!", ephemeral=True)
            return
        
        registered_teams[user_id] = self.team_name.value
        save_teams()
        
        embed = discord.Embed(title="✅ Регистрация завершена!", description=f"Команда **{self.team_name.value}** зарегистрирована!", color=0x2ecc71)
        embed.add_field(name="👑 Капитан:", value=self.captain_name.value, inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def delete_empty_clash(category, delay_seconds):
    await asyncio.sleep(delay_seconds)
    try:
        empty = True
        for channel in category.channels:
            if isinstance(channel, discord.VoiceChannel) and len(channel.members) > 0:
                empty = False
                break
        
        if empty:
            for channel in category.channels:
                await channel.delete()
            await category.delete()
    except:
        pass

# ===== ОБРАБОТЧИКИ СОБЫТИЙ =====
@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user} запущен!')
    print(f'✅ Загружено команд: {len(registered_teams)}')

@bot.event
async def on_message(message):
    violation = await mod_system.analyze_message(message)
    if violation:
        await message.delete()
        await mod_system.apply_punishment(message.author, violation, message.channel)
    await bot.process_commands(message)

# ===== КОМАНДЫ =====
@bot.tree.command(name="panel", description="📊 Установить панель для игроков")
async def setup_panel(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Нет прав!", ephemeral=True)
        return
    
    embed = discord.Embed(title="🎮 Панель управления командами", description="Все инструменты для организации игрового процесса", color=0x9b59b6)
    embed.add_field(name="📝 Регистрация команды", value="Зарегистрируйте команду для доступа ко всем функциям", inline=False)
    embed.add_field(name="🎮 Создать клоз", value="Приватная комната для матчей команда против команды", inline=False)
    embed.add_field(name="📊 Список команд", value="Посмотреть все зарегистрированные команды", inline=False)
    
    await interaction.channel.send(embed=embed, view=MainPanelView())
    await interaction.response.send_message("✅ Панель установлена!", ephemeral=True)

@bot.tree.command(name="modpanel", description="🛠️ Панель модерации")
@app_commands.checks.has_permissions(administrator=True)
async def admin_panel(interaction: discord.Interaction):
    embed = discord.Embed(title="🛠️ Панель модерации", description="Инструменты для управления заявками", color=0xe74c3c)
    embed.add_field(name="👁️ Просмотреть заявки", value="Список всех зарегистрированных команд", inline=False)
    embed.add_field(name="📤 Экспорт в файл", value="Скачать список команд", inline=False)
    embed.add_field(name="🗑️ Очистить заявки", value="Полная очистка базы", inline=False)
    
    await interaction.channel.send(embed=embed, view=AdminPanelView())
    await interaction.response.send_message("✅ Панель модерации установлена!", ephemeral=True)

@bot.tree.command(name="warn", description="Выдать предупреждение")
@app_commands.checks.has_permissions(manage_messages=True)
async def warn_user(interaction: discord.Interaction, пользователь: discord.Member, причина: str):
    await mod_system.apply_punishment(пользователь, "LEVEL1", interaction.channel, причина)
    await interaction.response.send_message(f"✅ {пользователь.mention} получил предупреждение", ephemeral=True)

@bot.tree.command(name="clear_warns", description="Сбросить предупреждения")
@app_commands.checks.has_permissions(administrator=True)
async def clear_warnings(interaction: discord.Interaction, пользователь: discord.Member):
    user_id = пользователь.id
    mod_system.warning_timestamps[user_id] = []
    embed = discord.Embed(title="✅ Предупреждения сброшены", color=0x2ecc71)
    embed.add_field(name="Участник", value=пользователь.mention, inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ===== ЗАПУСК =====
bot.run('ТВОЙ_ТОКЕН_БОТА')