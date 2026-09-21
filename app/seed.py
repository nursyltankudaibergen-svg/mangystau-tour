from . import db
from .models import SiteSetting,Tour
def seed_database():
 s={'brand_name':'MANGYSTAU','brand_subtitle':'TOUR','phone':'+7 700 000 00 00','hero_title':'ОТКРОЙ\nМАНГИСТАУ','hero_text':'Путешествуйте по самым красивым местам Мангистау с опытными гидами и максимальным комфортом.','hero_image':'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=2200&q=85','logo':'','whatsapp':'','instagram':''}
 for k,v in s.items():
  if not SiteSetting.query.filter_by(key=k).first(): db.session.add(SiteSetting(key=k,value=v))
 if not Tour.query.count():
  data=[('Бозжыра Grand Tour','5 дней / 4 ночи',250000,'Путешествие по Бозжыре и главным каньонам региона.','https://images.unsplash.com/photo-1500534623283-312aade485b7?auto=format&fit=crop&w=900&q=80','ХИТ',1),('Тузбаир & Кызылкуп','3 дня / 2 ночи',160000,'Белоснежные солончаки, пустынные пейзажи и закаты.','https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?auto=format&fit=crop&w=900&q=80','',2),('Шеркала и Торыш','4 дня / 3 ночи',190000,'Горы Шеркала, долина шаров и атмосферные дороги.','https://images.unsplash.com/photo-1500534314209-a25ddb2bd429?auto=format&fit=crop&w=900&q=80','',3),('Карынжарык Expedition','5 дней / 4 ночи',290000,'Экспедиционный маршрут для любителей дикой природы.','https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?auto=format&fit=crop&w=900&q=80','',4),('Жыгылган & Кок-Кала','3 дня / 2 ночи',150000,'Морские обрывы, каньоны и малоизвестные локации.','https://images.unsplash.com/photo-1501785888041-af3ef285b470?auto=format&fit=crop&w=900&q=80','',5)]
  for a in data: db.session.add(Tour(title=a[0],duration=a[1],price=a[2],description=a[3],image=a[4],badge=a[5],sort_order=a[6]))
 db.session.commit()
